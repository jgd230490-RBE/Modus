/*
 * ui_fix_configclp.js — the 9 Nov 2026 UI critique, wave 1, branch claude/ui-fix-config-clp, mounted in a real DOM (jsdom).
 *
 *   Finding 10 / card 10: Configuration for a planner (or any login that cannot save) is READ-ONLY from the top — one line
 *     says so, every field sits in ONE disabled fieldset (so a new field added to a tab falls into it with no extra work),
 *     no Save bar; a material's vehicles are a short summary, an admin opens the ticks with Edit in a row of their own.
 *     The planner's own actions (the community / collision fetches, the fuel settings) stay outside the fieldset.
 *   Finding 11 / card 11: CLP documents grouped by place (the site's CLP for all teams first, its team CLPs folded under
 *     it), each row's main button its NEXT STEP (Download draft in ⋯), a draft a hollow ring (the – circle read
 *     "blocked"); the reviewer's page one sentence that parses, a decision card under the title, Download a plain button.
 *   #46: the Locations material chips are tinted over the surface, so they read the same on a selected row.
 *
 * Its own file (the wave rule, notes\ui-critique-1109.md §H): nothing appended to dom_frontend.js / parse_frontend.js.
 * Needs typescript, react, react-dom, jsdom through NODE_PATH, like dom_frontend.js. Without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
const G = (() => { try { require.resolve("typescript"); return ""; } catch (e) { return "/home/claude/.npm-global/lib/node_modules/"; } })();
const ts = require(G + "typescript");
let JSDOM;
try { ({ JSDOM } = require(G + "jsdom")); } catch (e) { console.log("ui_fix_configclp.js: SKIPPED — jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const CLOCK = require(path.join(__dirname, "lib", "harness_clock.js"));
CLOCK.pinNode();

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const src = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1].replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const SEED = JSON.parse(fs.readFileSync(path.join(ROOT, "backend", "factors.json"), "utf8"));

const dom = new JSDOM(`<!doctype html><html><head></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require(G + "react"); w.ReactDOM = require(G + "react-dom/client");
w.fetch = () => new Promise(() => {});
w.mapboxgl = { Map: function(){ return { on(){}, remove(){}, getCanvas: () => ({ style: {} }), addControl(){}, getSource: () => null, getLayer: () => null, resize(){}, setStyle(){}, fitBounds(){} }; }, accessToken: "", NavigationControl: function(){}, ScaleControl: function(){} };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;
const act = w.React.act || require(G + "react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
w.localStorage.setItem("modus_theme", "light");
w.eval(CLOCK.shiftSource());
w.eval(js + "\nwindow.__TENANT = TENANT; window.__ACCESS = ACCESS; window.__rvScheme = rvScheme; window.__vehLabel = vehLabel;");   // consts live in the script scope

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const settle = (ms) => act(async () => { await sleep(ms || 10); });
const reply = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status,
  text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)), json: () => Promise.resolve(body),
  blob: () => Promise.resolve(new w.Blob(["x"])), headers: { get: () => null } });
const press = async (b) => { await act(async () => { b.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); }); await settle(10); };
const btnT = (el, re) => [...el.querySelectorAll("button")].find(b => re.test(b.textContent.trim()));
const mount = async (comp, props) => {
  const el = w.document.createElement("div"); w.document.body.appendChild(el); const r = w.ReactDOM.createRoot(el);
  await act(async () => { r.render(w.React.createElement(comp, props)); }); await settle(20);
  return { el, done: async () => { await act(async () => { r.unmount(); }); el.remove(); } };
};

const PLANNER = { role: "planner", label: "Planner", ipt: null, can_approve: true, ipt_locked: false, ipt_required: true, demo: false, ipts: ["IPT1", "IPT2"] };
const ADMIN_CODE = { ...PLANNER, role: "admin", label: "Admin" };                 // a shared admin CODE cannot save either
const ADMIN_LOGIN = { ...ADMIN_CODE, via: "login" };

// ================================================================ 1. Configuration, read-only (card 10)
async function configReadOnly(){
  const DOC = JSON.parse(JSON.stringify(SEED));
  DOC.planning = { ...(DOC.planning || {}), count_visit_as: 2 };
  w.fetch = (url) => {
    const u = String(url);
    if (/\/api\/config\/factors$/.test(u)) return reply(200, { doc: DOC, status: { source: "db", updated_at: "2026-11-08T20:19:00Z", updated_by: "x" }, file: SEED });
    if (/\/api\/costing$/.test(u)) return reply(200, { target: { rate_eur_per_load: 120 }, summary: null });
    return new Promise(() => {});
  };
  const tab = async (m, label) => { await press(btnT(m.el, new RegExp("^" + label + "$"))); };
  const fs_ = (m) => [...m.el.querySelectorAll("fieldset[data-cfg-fields]")];
  // every control a person could change, outside the planner's own panels (the fetches, the fuel settings)
  const loose = (m) => [...m.el.querySelectorAll(".cfg-main input, .cfg-main select, .cfg-main textarea")]
    .filter(x => !x.closest("fieldset[data-cfg-fields]") && !x.closest('[data-cfg="community"], [data-cfg="collisions"], [data-fuel-widget], .fuel-widget') && !x.readOnly);

  for (const [who, acc] of [["a planner", PLANNER], ["an admin by the shared code", ADMIN_CODE]]) {
    const m = await mount(w.ConfigPage, { meta: {}, who: "tester", access: acc });
    const note = m.el.querySelector("[data-cfg-readonly]");
    ok(`⭐ CONFIG RO: ${who} — one line at the top, 'You can read the configuration. An admin changes it.', and no Save bar, no More menu`,
       !!note && note.textContent === "You can read the configuration. An admin changes it." && !m.el.querySelector("[data-cfg-savebar]")
       && !m.el.querySelector("[data-cfg-more]") && !btnT(m.el, /^Save$/) && !/Only an admin can save/.test(m.el.textContent)
       && !/Changes apply on save/.test(m.el.textContent));
    const sections = [];
    for (const [label, key] of [["Vehicles", "vehicles"], ["Materials", "materials"], ["Planning", "planning"], ["Costing · fuel", "costing"],
                                ["Seasonal restrictions", "seasonal"], ["Map and bulletin", "mapbulletin"]]) {
      await tab(m, label.replace(/[·]/g, "\\$&"));
      const f = fs_(m);
      sections.push([key, f.length, f.every(x => x.disabled && x.dataset.cfgFields === "read"), loose(m).length,
                     m.el.querySelectorAll(".cfg-main fieldset[data-cfg-fields] input, .cfg-main fieldset[data-cfg-fields] select").length]);
    }
    ok(`⭐ CONFIG RO: ${who} — on every section the fields sit in a DISABLED fieldset (data-cfg-fields="read"), and no control a person could change is left outside it`,
       sections.every(([k, n, all, lo, inside]) => n >= 1 && all && lo === 0 && (inside > 0 || k === "seasonal")), JSON.stringify(sections));
    await tab(m, "Everything \\(JSON\\)");
    const ta = m.el.querySelector(".cfg-main textarea");
    ok(`CONFIG RO: ${who} — Everything (JSON) is read only`, !!ta && ta.readOnly === true);
    ok(`CONFIG RO: ${who} — no Organisation file tab (admins only)`, !btnT(m.el, /^Organisation file$/));
    await tab(m, "Map and bulletin");
    const ex = [...m.el.querySelectorAll(".cfg-main [data-ph-example]")];
    ok(`CONFIG RO: ${who} — Map and bulletin's empty example fields read '—' (no made-up example shown as a value)`,
       ex.length >= 3 && ex.filter(x => !x.value).every(x => x.placeholder === "—"), ex.map(x => x.placeholder).join("|"));
    await m.done();
  }

  // the vehicles: a planner reads a summary, no English column, no Edit
  {
    const m = await mount(w.ConfigPage, { meta: {}, who: "tester", access: PLANNER });
    const th = [...m.el.querySelectorAll(".cfg-main table.tbl thead th")].map(x => x.textContent.trim());
    ok("CONFIG RO: Vehicles — the English column (a typing column) is left out for a reader", th.includes("Vehicle") && !th.includes("English"), th.join("|"));
    await tab(m, "Materials");
    const k = Object.keys(DOC.material_categories).find(x => !x.startsWith("_") && (DOC.material_categories[x].vehicles || []).length >= 2);
    const sum = m.el.querySelector(`[data-cfg-veh-sum="${k}"]`);
    const want = Object.keys(DOC.vehicles).filter(v => !v.startsWith("_") && DOC.material_categories[k].vehicles.includes(v)).map(v => w.__vehLabel(v)).join(", ");
    ok("⭐ CONFIG RO: Materials — each material's vehicles as a short summary, in the Configuration's order; no Edit, no tick grid",
       !!sum && sum.textContent === want && !m.el.querySelector("[data-cfg-veh-edit]") && !m.el.querySelector("[data-cfg-veh-grid]")
       && !m.el.querySelector('.cfg-main input[type="checkbox"]:not(:disabled)'), sum ? sum.textContent : "no summary");
    await tab(m, "Planning");
    ok("CONFIG RO: Planning — the count of a coming and going reads as its chosen words",
       /2 movements, in and out/.test(m.el.querySelector(".cfg-main").textContent));
    await tab(m, "Costing · fuel".replace(/[·]/g, "\\$&"));
    await settle(20);
    const tr = btnT(m.el, /^Save target rate$/);
    ok("CONFIG RO: Costing — the target rate is inside the read-only fieldset (its Save is not pressable)", !!tr && !!tr.closest("fieldset[data-cfg-fields='read']") && tr.closest("fieldset").disabled === true && tr.matches(":disabled"));
    await m.done();
  }

  // an admin LOGIN edits as before; the vehicles open with Edit in a row of their own
  {
    const m = await mount(w.ConfigPage, { meta: {}, who: "tester", access: ADMIN_LOGIN });
    ok("⭐ CONFIG EDIT: an admin login — no read-only line, the fields enabled (data-cfg-fields=\"edit\"), the Save bar and More",
       !m.el.querySelector("[data-cfg-readonly]") && fs_(m).every(x => !x.disabled && x.dataset.cfgFields === "edit") && !!m.el.querySelector("[data-cfg-savebar]")
       && !!m.el.querySelector("[data-cfg-more]") && /Changes apply on save/.test(m.el.textContent));
    const th = [...m.el.querySelectorAll(".cfg-main table.tbl thead th")].map(x => x.textContent.trim());
    ok("CONFIG EDIT: Vehicles keep the English column for an admin", th.includes("English"));
    await tab(m, "Materials");
    const k = Object.keys(DOC.material_categories).find(x => !x.startsWith("_") && (DOC.material_categories[x].vehicles || []).length >= 2);
    const ed = m.el.querySelector(`[data-cfg-veh-edit="${k}"]`);
    ok("CONFIG EDIT: each material's summary has an Edit button that names the material and controls a row not yet drawn",
       !!ed && ed.textContent === "Edit" && ed.getAttribute("aria-expanded") === "false" && ed.getAttribute("aria-label") === `Edit the vehicles for ${k}`
       && !m.el.querySelector(`[data-cfg-veh-grid="${k}"]`));
    await press(ed);
    const grid = m.el.querySelector(`[data-cfg-veh-grid="${k}"]`);
    ok("⭐ CONFIG EDIT: Edit opens a row of its own under the material, the whole card wide (colspan 6), a tick per vehicle; the button reads Done",
       !!grid && grid.previousElementSibling && grid.previousElementSibling.contains(ed) && grid.querySelector("td").colSpan === 6
       && grid.querySelectorAll('input[type="checkbox"]').length === Object.keys(DOC.vehicles).filter(v => !v.startsWith("_")).length
       && ed.textContent === "Done" && ed.getAttribute("aria-expanded") === "true" && ed.getAttribute("aria-controls") === grid.id
       && ed.getAttribute("aria-label") === `Done with the vehicles for ${k}`);
    const off = grid.querySelector('input[type="checkbox"]:not(:checked)');
    const before = m.el.querySelector(`[data-cfg-veh-sum="${k}"] span`).textContent;
    await press(off);
    const save = btnT(m.el, /^Save$/);
    ok("⭐ CONFIG EDIT: ticking a vehicle adds it to the summary and makes the page's Save pressable",
       m.el.querySelector(`[data-cfg-veh-sum="${k}"] span`).textContent !== before && !!save && !save.disabled);
    await press(ed);
    ok("CONFIG EDIT: Done folds the row again", !m.el.querySelector(`[data-cfg-veh-grid="${k}"]`));
    await m.done();
  }
}

// ================================================================ 2. the source rules behind it
function sourceRules(){
  ok("⭐ CONFIG RO (source): one CfgFields component — a fieldset, disabled for a reader, the read-only look by class",
     src.includes('function CfgFields({ ro, children }){') && src.includes('<fieldset className={"cfg-fs" + (ro ? " cfg-ro" : "")} disabled={!!ro} data-cfg-fields={ro ? "read" : "edit"}><CfgRO.Provider value={!!ro}>{children}</CfgRO.Provider></fieldset>'));
  ok("CONFIG RO (source): read-only = not an admin login (the server's own rule for saving)", src.includes("const canSave = isAdminLogin(access);") && src.includes("const ro = !canSave;"));
  ok("⭐ CONFIG RO (source): the Save bar is an admin's only; the planner's foot line is gone",
     src.includes('{tab !== "orgfile" && canSave && (') && !src.includes("Only an admin can save the configuration."));
  ok("CONFIG RO (source): the planner's own actions stay outside the fieldset — the community and collision fetches and the fuel settings",
     /<\/CfgFields>\n[^\n]*\n?[\s\S]{0,400}<CommunityPanel access=\{access\} \/>/.test(src)
     && /<\/div><\/CfgFields>\n\s*\{\/\* 9 Nov 2026 \(card 10\): the fuel settings[^\n]*\*\/\}\n\s*<div>\n[^\n]*\n\s*<FuelWidget mode="config"/.test(src));
  ok("⭐ CONFIG RO (CSS): the read-only look — fields as text, ticks as ✓ / –, the chosen radio only, buttons hidden, examples hidden",
     html.includes(".cfg-fs{border:0;margin:0;padding:0;min-width:0;}") && html.includes(".cfg-ro-note{")
     && /\.cfg-ro button,\s*\.cfg-ro \[data-ro-hide\]\{display:none;\}/.test(html)
     && /\.cfg-ro input\[type=checkbox\]:not\(\.hidden\)\{[^}]*appearance:none/.test(html) && /content:"✓"/.test(html) && /content:"–"/.test(html));
  ok("CONFIG RO (source): the made-up examples (contact, privacy, imagery, day hire) are marked data-ph-example and read '—' for a reader, never as values",
     (src.match(/data-ph-example="1"/g) || []).length >= 6 && (src.match(/placeholder=\{ro \? "—" : /g) || []).length === 6
     && src.includes("const CfgRO = React.createContext(false);") && src.includes("const ro = React.useContext(CfgRO);"));

  // CLP list (card 11)
  ok("⭐ CLP LIST (source): the Covers and Cover columns are gone; five heads — CLP, Status, Last issue, Tasks, Next step (for a screen reader)",
     src.includes('<thead><tr><th scope="col">CLP</th><th scope="col">Status</th><th scope="col">Last issue</th><th scope="col">Tasks</th><th scope="col"><span className="sr-only">Next step</span></th></tr></thead>'));
  ok("⭐ CLP LIST (source): Download draft is the first line of every row's ⋯ (never the main button)",
     /<RowMenu name=\{c\.name \+ " · " \+ teamWord\(c\)\}>\n\s*<button type="button" onClick=\{\(\) => draft\(c\)\} disabled=\{!!building\}>Download draft<\/button>/.test(src)
     && !/data-clp-primary[^>]*>Download draft/.test(src));
  ok("CLP LIST (CSS): the draft ring — hollow, no glyph", html.includes(".row-st.rs-draft i{background:transparent;border:2px solid var(--chart-none);") && src.includes('draft: ""'));

  // reviewer (card 11)
  ok("⭐ REVIEW (source): rvScheme turns a demo name's '— demo scheme' into '(demo)' and leaves other names alone",
     w.__rvScheme("Wolds Link dualling — demo scheme") === "Wolds Link dualling (demo)" && w.__rvScheme("Wolds Link dualling - fictional demo scheme") === "Wolds Link dualling (demo)"
     && w.__rvScheme("A14 upgrade") === "A14 upgrade" && w.__rvScheme("") === "");

  // #46
  const cc = src.slice(src.indexOf("function CatChips("), src.indexOf("function CatChips(") + 1200);
  ok("⭐ #46 (source): the material chips' tint is laid over the surface (a linear-gradient on var(--surface)), the out chip's tint the accent's own",
     cc.includes('const tint = dir === "in" ? "rgba(3,158,134,.10)" : "var(--navy-soft)";') && cc.includes("const bg = `linear-gradient(${tint}, ${tint}), var(--surface)`;")
     && !cc.includes("rgba(37,99,235"));
}

// ================================================================ 3. the CLP list, mounted (card 11)
async function clpList(){
  const FIELDS = ["address", "postcode", "landowner", "site_use", "summary", "manager_name", "manager_phone", "manager_email", "provider_name", "provider_phone", "provider_email"].map(k => ({ key: k, label: k }));
  const row = (id, loc, name, team, team_name, status, extra) => ({ id, name, auto: true, saved: false, location_ids: [loc], places: [{ id: loc, name, type: "site" }], types: ["site"],
    team, team_name, impact: "higher", cover: {}, cover_typed: 0, cover_total: 11, status, status_word: { draft: "Draft", sent: "Sent", changes: "Changes asked", approved: "Approved" }[status],
    sent_by: null, sent_at: null, changes_note: null, busiest_label: "Apr 2027", issues: 0, last_issue: null, next_issue: 1,
    tasks: { open: 0, overdue: 0, next_due: null, notes: 0, done: 0, mine_open: 0 }, ...(extra || {}) });
  const ALL = [row("auto-L001-all", "L001", "Harborough Compound", null, null, "draft", { cover_typed: 3 }),
               row("auto-L001-IPT1", "L001", "Harborough Compound", "IPT1", "North Team", "draft"),
               row("auto-L001-IPT2", "L001", "Harborough Compound", "IPT2", "Central Team", "approved", { issues: 1, last_issue: { no: 1, date: "2026-10-25" }, next_issue: 2 }),
               row("auto-L019-all", "L019", "Tilton Viaduct site", null, null, "draft", { cover_typed: 11 }),
               row("auto-L019-IPT1", "L019", "Tilton Viaduct site", "IPT1", "North Team", "changes", { cover_typed: 11, changes_note: "Add the Saturday hours" })];
  const base = { cover_fields: FIELDS, places: [], teams: [{ id: "IPT1", name: "North Team" }, { id: "IPT2", name: "Central Team" }],
    statuses: ["draft", "sent", "changes", "approved"].map(k => ({ key: k, word: k })) };
  let acc = PLANNER;
  w.fetch = (url, o) => {
    const u = String(url), method = (o && o.method) || "GET";
    if (u === "/api/clp/documents" && method === "GET")
      return reply(200, acc.ipt ? { ...base, clps: ALL.filter(c => c.team === acc.ipt), can_approve: false, team: acc.ipt, team_name: "North Team", review_groups: false }
                                : { ...base, clps: ALL, can_approve: true, team: null, team_name: null, review_groups: false });
    return new Promise(() => {});
  };
  const rows = (el) => [...el.querySelectorAll("[data-clp-row]")];
  const prim = (el, id) => el.querySelector(`[data-clp-row="${id}"] [data-clp-primary]`);

  const p = await mount(w.ClpPage, { access: PLANNER });
  const groups = [...p.el.querySelectorAll("[data-clp-group]")];
  ok("⭐ CLP LIST: a planner — one group a place, the site's CLP for all teams first, its team CLPs under it",
     groups.length === 2 && groups.map(g => [...g.querySelectorAll("[data-clp-row]")].map(r => r.getAttribute("data-clp-row")).join(",")).join(" / ")
       === "auto-L001-all,auto-L001-IPT1,auto-L001-IPT2 / auto-L019-all,auto-L019-IPT1",
     groups.map(g => [...g.querySelectorAll("[data-clp-row]")].map(r => r.getAttribute("data-clp-row")).join(",")).join(" / "));
  const f1 = groups[0].querySelector("[data-clp-fold]"), f2 = groups[1].querySelector("[data-clp-fold]");
  ok("⭐ CLP LIST: a group with nothing waiting on an approver is folded ('▸ 2 team CLPs'); one whose team CLP has changes asked is open",
     f1.getAttribute("aria-expanded") === "false" && f1.textContent.trim() === "▸ 2 team CLPs" && groups[0].querySelectorAll("[data-clp-child][hidden]").length === 2
     && f2.getAttribute("aria-expanded") === "true" && groups[1].querySelectorAll("[data-clp-child][hidden]").length === 0, f1.textContent + " | " + f2.textContent);
  ok("⭐ CLP LIST: the next step — 'Fill in the cover (3 of 11)' while the cover is short, 'Approve as Issue 1…' once it is whole; a team CLP under its site offers no main button but its cover count",
     prim(p.el, "auto-L001-all").textContent === "Fill in the cover (3 of 11)" && prim(p.el, "auto-L001-all").className === "btn-sec"
     && prim(p.el, "auto-L019-all").textContent === "Approve as Issue 1…" && prim(p.el, "auto-L019-all").className === "btn-pri"
     && !prim(p.el, "auto-L001-IPT1") && p.el.querySelector('[data-clp-row="auto-L001-IPT1"] [data-clp-cover-left]').textContent === "Cover 0 of 11"
     && !prim(p.el, "auto-L001-IPT2") && !p.el.querySelector('[data-clp-row="auto-L001-IPT2"] [data-clp-cover-left]'));
  ok("CLP LIST: the main button is never Download; each row's ⋯ starts with Download draft",
     ![...p.el.querySelectorAll("[data-clp-primary]")].some(b => /Download/.test(b.textContent))
     && rows(p.el).every(r => r.querySelector("details.row-menu button").textContent === "Download draft"));
  ok("CLP LIST: an Approve that is the main button is not repeated in the ⋯",
     ![...p.el.querySelectorAll('[data-clp-row="auto-L019-all"] details.row-menu button')].some(b => /^Approve as Issue/.test(b.textContent)));
  ok("⭐ CLP LIST: a draft's status is the hollow ring (rs-draft), never the – circle",
     p.el.querySelector('[data-clp-row="auto-L001-all"] [data-row-status]').getAttribute("data-row-status") === "draft"
     && p.el.querySelector('[data-clp-row="auto-L001-all"] [data-row-status] i').textContent === ""
     && !p.el.querySelector('[data-clp-row] [data-row-status="none"]'));
  ok("CLP LIST: the site's line names whose lorries ('all teams'); a team CLP's own name is its team", /all teams/.test(rows(p.el)[0].textContent)
     && p.el.querySelector('[data-clp-row="auto-L001-IPT1"] td button.row-open').textContent === "North Team" && !/IPT\d/.test(p.el.textContent));
  await press(f1);
  ok("CLP LIST: the fold opens the site's team CLPs", f1.getAttribute("aria-expanded") === "true" && groups[0].querySelectorAll("[data-clp-child][hidden]").length === 0);
  const st = p.el.querySelector("[data-clp-filters] select:nth-of-type(1)");
  const sel = [...p.el.querySelectorAll("[data-clp-filters] select")][1];
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLSelectElement.prototype, "value").set.call(sel, "draft"); sel.dispatchEvent(new w.Event("change", { bubbles: true })); });
  await settle(10);
  ok("CLP LIST: with a filter set the matching CLPs are listed flat (no folds), each with its own next step",
     !p.el.querySelector("[data-clp-fold]") && rows(p.el).length === 3 && !rows(p.el).some(r => r.hidden) && !!prim(p.el, "auto-L001-IPT1")
     && prim(p.el, "auto-L001-IPT1").textContent === "Fill in the cover (0 of 11)");
  await p.done();

  acc = { role: "ipt", label: "North Team", ipt: "IPT1", can_approve: false, ipt_locked: true, ipt_required: false, demo: false, ipts: ["IPT1"] };
  const t = await mount(w.ClpPage, { access: acc });
  ok("⭐ CLP LIST: a team — its own CLPs, no folds; 'Fill in the cover (0 of 11)' where the cover is short, 'Send for approval…' where it is whole",
     rows(t.el).length === 2 && !t.el.querySelector("[data-clp-fold]") && prim(t.el, "auto-L001-IPT1").textContent === "Fill in the cover (0 of 11)"
     && prim(t.el, "auto-L019-IPT1").textContent === "Send for approval…"
     && ![...t.el.querySelectorAll('[data-clp-row="auto-L019-IPT1"] details.row-menu button')].some(b => /^Send for approval/.test(b.textContent)));
  await t.done();
}

// ================================================================ 4. the reviewer's page (card 11)
async function reviewer(){
  const REVIEWER = { via: "reviewer", reviewer: true, name: "Hana Highways", group_name: "Highways client (fictional)", role: null, can_approve: false, user_id: "r1", ipts: [] };
  const LIST = { group_name: "Highways client (fictional)", scheme: "Wolds Link dualling — demo scheme",
    clps: [{ id: "c1", name: "Tilton Viaduct site", team_name: "North Team", issue_no: 2, sent_at: "2026-10-31T09:00:00Z", sent_by: "Pat Planner", state: "waiting", tasks_open: 0 }] };
  const ONE = { id: "c1", name: "Tilton Viaduct site", team_name: "North Team", group_name: "Highways client (fictional)", can_decide: true,
    latest: { no: 2, sent_at: "2026-10-31T09:00:00Z", sent_by: "Pat Planner", note: null, state: "waiting" },
    issues: [{ no: 2, sent_at: "2026-10-31T09:00:00Z", sent_by: "Pat Planner", decisions: [] }], thread: [], tasks: [], for_options: [], task_counts: { ours: 0, theirs: 0 } };
  const calls = [];
  w.fetch = (url, o) => {
    const u = String(url), method = (o && o.method) || "GET"; calls.push({ u, method, body: o && o.body ? JSON.parse(o.body) : null });
    if (/\/api\/review\/clps$/.test(u)) return reply(200, LIST);
    if (/\/api\/review\/clps\/c1$/.test(u)) return reply(200, ONE);
    if (/\/api\/review\/clps\/c1\/decision$/.test(u)) return reply(200, { ...ONE, latest: { ...ONE.latest, state: "returned", by: "Hana Highways", at: "2026-10-31T10:00:00Z" } });
    return new Promise(() => {});
  };
  const m = await mount(w.ReviewPage, { role: REVIEWER });
  ok("⭐ REVIEW: one sentence that parses — 'Plans that Wolds Link dualling (demo) has sent to you.'",
     /Plans that Wolds Link dualling \(demo\) has sent to you\./.test(m.el.textContent) && !/demo scheme has sent/.test(m.el.textContent));
  await press(m.el.querySelector('[data-review-row="c1"] button.row-open'));
  const dl = m.el.querySelector("[data-review-download]"), dec = m.el.querySelector("[data-review-decision]");
  ok("⭐ REVIEW: Download Issue 2 is a plain button; the decision card follows it, before the notes",
     !!dl && dl.className === "btn-sec" && /Download Issue 2 \(Word\)/.test(dl.textContent) && !!dec
     && !!(dl.compareDocumentPosition(dec) & w.Node.DOCUMENT_POSITION_FOLLOWING) && /Your decision on Issue 2/.test(dec.textContent)
     && m.el.querySelectorAll(".btn-pri").length === 1 && dec.contains(m.el.querySelector(".btn-pri")));
  ok("REVIEW: Accept and Return live only on the decision card (none at the foot of the notes)",
     m.el.querySelectorAll("[data-review-accept]").length === 1 && dec.contains(m.el.querySelector("[data-review-accept]"))
     && m.el.querySelectorAll("[data-review-return]").length === 1 && dec.contains(m.el.querySelector("[data-review-return]")));
  await press(dec.querySelector("[data-review-return]"));
  const box = dec.querySelector("#rv-ret");
  await act(async () => { Object.getOwnPropertyDescriptor(w.HTMLTextAreaElement.prototype, "value").set.call(box, "Add the Saturday hours"); box.dispatchEvent(new w.Event("input", { bubbles: true })); });
  ok("REVIEW: the Return box is labelled 'What needs changing' and its button wakes once something is written",
     dec.querySelector('label[for="rv-ret"]').textContent === "What needs changing" && !dec.querySelector("[data-review-return-go]").disabled);
  await press(dec.querySelector("[data-review-return-go]"));
  const dc = calls.find(c => /\/decision$/.test(c.u) && c.method === "POST");
  ok("⭐ REVIEW: Return Issue 2 posts 'returned' with the box's words, says so and closes the box",
     !!dc && dc.body.issue_no === 2 && dc.body.decision === "returned" && dc.body.words === "Add the Saturday hours"
     && /Issue 2 returned with your comments\./.test(m.el.textContent) && !m.el.querySelector("#rv-ret"));
  await m.done();
}

(async () => {
  sourceRules();
  for (const [name, fn] of [["CONFIG", configReadOnly], ["CLP LIST", clpList], ["REVIEW", reviewer]]) {
    try { await fn(); ok(`${name}: the section ran to the end`, true); }
    catch (e) { ok(`${name}: the section ran to the end`, false, String(e && e.stack || e).slice(0, 600)); }
  }
  for (const f of fail) console.log("  FAIL: " + f);
  console.log(`${pass} passed, ${fail.length} failed`);
  process.exit(fail.length ? 1 : 0);
})();
