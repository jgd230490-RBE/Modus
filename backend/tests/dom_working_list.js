/*
 * dom_working_list.js — the "Working" list on the page (23 Nov 2026, branch claude/working-list; John's "Yes, as
 * recommended" to Q1 to Q8 of the mockup notes\working-list-mockup-1121, Option A). The staff app's own script run in a
 * real DOM (jsdom), the header mounted, the server stood in for by a fetch this file answers.
 *
 *   1  the chip: NOTHING in the header while the list is empty; "Working · 1" (amber), "Stopped · 1" (red), "Done · 1"
 *      (green), the most pressing state winning; for staff on the app's pages only
 *   2  the list: headed "Working", the "i" box with the mockup's 24 words and its guide link; a running row (line, thin
 *      bar, "Started 14:21", who started it only as the row's title); a done row with a named "×" that closes it for
 *      everyone; a stopped row with what is kept and "Carry on" only where the server says this person may
 *   3  a click on a row goes to the page its job runs on, only where this sign-in has that page
 *   4  "Carry on": a page-sent job is handed to its own page (which runs the same action again); a server-run one is
 *      started again from the list, and a refusal is shown as the server's sentence alone
 *   5  Q7: the browser's "Leave site?" question is armed ONLY while this page is sending a job; a tab that goes says so
 *   6  the refusal: status 423 gives the server's sentence alone, anything else does not
 *   7  the line where the action was pressed is the list's line (source level: the three old shapes are gone, each
 *      loop starts and ends its row, the finished and failed messages are kept)
 *
 * NOT covered here: the Routes, Zones, Look-ahead and Config pages are not mounted (their loops are read at source
 * level; a real Route all needs a routing key). No real browser: the native "Leave site?" dialog itself, the chip's
 * colours on screen and the list's place under the chip are in the pictures (notes\working-list-mockup-1121\real).
 * Needs typescript, react, react-dom and jsdom through NODE_PATH; without jsdom it prints SKIPPED.
 */
const fs = require("fs");
const path = require("path");
let ts, JSDOM;
try { ts = require("typescript"); ({ JSDOM } = require("jsdom")); }
catch (e) { console.log("dom_working_list.js: SKIPPED — typescript / jsdom not installed"); process.exit(0); }

let pass = 0; const fail = [];
const ok = (label, cond, extra) => { if (cond) pass++; else fail.push(label + (extra ? "  " + extra : "")); };

const ROOT = path.resolve(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const code = html.match(/<script type="text\/babel"[^>]*>([\s\S]*?)<\/script>/)[1];
const src = code.replace(/^ReactDOM\.createRoot\([\s\S]*?\);\s*$/m, "");
const js = ts.transpileModule(src, { compilerOptions: { jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.None } }).outputText;
const slice = (a, b) => { const i = code.indexOf(a); const j = code.indexOf(b, i + a.length); return i < 0 || j < 0 ? "" : code.slice(i, j); };

const dom = new JSDOM(`<!doctype html><html><head><meta name="theme-color" content="#1F2024"></head><body><div id="root"></div></body></html>`,
                      { runScripts: "outside-only", pretendToBeVisual: true, url: "https://wayscope.test/" });
const w = dom.window;
for (const k of ["window", "document", "navigator", "localStorage", "getComputedStyle", "HTMLElement", "MouseEvent", "KeyboardEvent"]) global[k] = w[k];
w.React = require("react"); w.ReactDOM = require("react-dom/client");
w.mapboxgl = { Map: function(){ return { on(){}, remove(){}, getCanvas: () => ({ style: {} }), addControl(){}, getSource: () => null, getLayer: () => null, resize(){}, setStyle(){}, fitBounds(){} }; }, accessToken: "" };
w.Chart = function(){ return { destroy(){}, update(){} }; }; w.Chart.defaults = {};
w.HTMLCanvasElement.prototype.getContext = () => null;

// ---- the server, stood in for ---------------------------------------------------------------------------------------
const S = { list: { jobs: [], busy: {}, running: null }, start: null, refresh: null, calls: [] };
const reply = (status, body) => Promise.resolve({ ok: status >= 200 && status < 300, status, url: "", json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
w.fetch = (url, opts) => {
  const u = String(url), o = opts || {}, m = (o.method || "GET").toUpperCase();
  let body = null; try { body = o.body ? JSON.parse(o.body) : null; } catch (e) {}
  S.calls.push({ u, m, body, keepalive: !!o.keepalive, guard: (o.headers || {})["X-Wayscope"] });
  if (/\/working$/.test(u) && m === "GET") return reply(200, S.list);
  if (/\/working\/start$/.test(u)) return S.start ? S.start(body) : reply(500, {});
  if (/\/working\/[^/]+\/end$/.test(u)) return reply(200, {});
  if (/\/working\/[^/]+\/close$/.test(u)) { const id = decodeURIComponent(u.split("/").slice(-2)[0]); S.list = { ...S.list, jobs: S.list.jobs.filter(j => j.id !== id) }; return reply(200, S.list); }
  if (/\/(community|collisions)\/refresh$/.test(u) || /restrictions\/refresh$/.test(u)) return S.refresh ? S.refresh(u) : reply(200, { started: true });
  return new Promise(() => {});
};
const act = w.React.act || require("react-dom/test-utils").act;
w.IS_REACT_ACT_ENVIRONMENT = true; global.IS_REACT_ACT_ENVIRONMENT = true;
const flush = () => act(async () => { for (let i = 0; i < 6; i++) await new Promise(r => setTimeout(r, 0)); });
const click = (el) => act(async () => { el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); for (let i = 0; i < 6; i++) await new Promise(r => setTimeout(r, 0)); });

let booted = true;
try { w.eval(js + "\ntry { window.__INFO = INFO; window.__WORK_CARRY = WORK_CARRY; } catch (e) {}"); } catch (e) { booted = false; fail.push("the page's script runs in jsdom  " + String(e && e.message).slice(0, 200)); }
const HAS = booted && typeof w.workApply === "function" && typeof w.WorkChip === "function" && !!w.WORK;
ok("⭐ the page has the Working list's one store and its chip (WORK, workApply, WorkChip)", HAS);

const T0 = "2026-11-23T14:21:00Z", T1 = "2026-11-23T14:02:00Z", T2 = "2026-11-23T14:26:00Z";
const RUN = { id: "j1", kind: "route_all", state: "running", line: "Route all: 62 of 188 legs", done: 62, total: 188, started_at: T0, ended_at: null,
              by: "Ada Admin", page: "routes", kept: "", sent_by: "page", can_carry: false, can_close: false, args: { profiles: ["A", "B"], legs: "" } };
const DONE = { id: "j2", kind: "make_primary", state: "done", line: "R050: Alt 1 made the main route", done: 0, total: null, started_at: T1, ended_at: T1,
               by: "Ada Admin", page: "routes", kept: "", sent_by: "held", can_carry: false, can_close: true, args: {} };
const STOP = { id: "j3", kind: "route_all", state: "stopped", line: "Route all stopped at 62 of 188 legs", done: 62, total: 188, started_at: T0, ended_at: T2,
               by: "Ada Admin", page: "routes", kept: "the routes worked out are kept", sent_by: "page", can_carry: true, can_close: false, args: { profiles: ["A", "B"], legs: "loaded" } };
const FETCH_STOP = { id: "community@x", kind: "community", state: "stopped", line: "Community places: fetch stopped", done: 0, total: null, started_at: T0, ended_at: T2,
                     by: "Pat Planner", page: "config", kept: "", sent_by: "server", can_carry: true, can_close: false, args: {} };
const SENT = "Busy-hour times are running. Route all can start when they finish.";

(async () => {
  if (HAS) {
    const ADMIN = { via: "login", role: "admin", name: "Ada Admin", can_approve: true };
    const box = w.document.getElementById("root");
    const root = w.ReactDOM.createRoot(box);
    const mount = (view, role) => act(async () => { root.render(w.React.createElement(w.Header, { view, role, setView(){}, signOut(){}, vehLang: "en", setVehLang(){} })); });
    const set = async (jobs, busy, running) => { S.list = { jobs, busy: busy || {}, running: running || null }; await act(async () => { w.workApply(S.list); }); await flush(); };
    const chip = () => box.querySelector("[data-work-chip]");
    const rows = () => [...box.querySelectorAll("[data-work-row]")];

    // ------------------------------------------------------------ 1. the chip
    await mount("portal", ADMIN); await flush();
    ok("⭐ 1. nothing running: NO chip and no word of it in the header", !chip() && !/Working|Done ·|Stopped/.test(box.querySelector("header").textContent)
       && !box.querySelector(".work-list"));
    ok("1. the header asks the server for the list (GET /api/working) as it mounts", S.calls.some(c => /\/working$/.test(c.u) && c.m === "GET"));
    await set([RUN], { route_all: "Route all is running. Route all can start when it finishes." }, "route_all");
    ok("⭐ 1. a job running: the chip reads 'Working · 1', amber", !!chip() && chip().textContent === "Working · 1"
       && chip().getAttribute("data-work-chip") === "warn" && chip().classList.contains("wc-warn"), chip() && chip().textContent);
    ok("1. the chip is a real button in the header, before the account menu and Sign out, closed until pressed",
       chip().tagName === "BUTTON" && !!chip().closest("header") && chip().getAttribute("aria-expanded") === "false"
       && [...box.querySelectorAll("header button")].indexOf(chip()) < [...box.querySelectorAll("header button")].findIndex(b => /Sign out/.test(b.textContent)));
    await set([STOP]);
    ok("⭐ 1. only a stopped job: 'Stopped · 1', red", chip().textContent === "Stopped · 1" && chip().classList.contains("wc-bad"));
    await set([DONE]);
    ok("⭐ 1. only a finished job: 'Done · 1', green", chip().textContent === "Done · 1" && chip().classList.contains("wc-ok"));
    await set([RUN, STOP, DONE]);
    ok("1. the most pressing state wins: running over stopped over done; the count is that state's lines",
       chip().textContent === "Working · 1" && (await set([STOP, DONE]), chip().textContent === "Stopped · 1")
       && (await set([DONE, { ...DONE, id: "j9" }]), chip().textContent === "Done · 2"));
    await set([]);
    ok("⭐ 1. the list empty again: the chip is gone", !chip());
    await set([RUN], {}, "route_all");
    await mount("public", null); await flush();
    const noChipPublic = !chip();
    await mount("review", { via: "reviewer", name: "Rae Reviewer" }); await flush();
    ok("1. no chip on the public map, nor for a client reviewer", noChipPublic && !chip());
    await mount("portal", ADMIN); await flush();
    await set([RUN, DONE], { route_all: "x" }, "route_all");

    // ------------------------------------------------------------ 2. the list
    ok("2. the list is closed until the chip is pressed", !box.querySelector("[data-work-list]"));
    await click(chip());
    const list = () => box.querySelector("[data-work-list]");
    ok("⭐ 2. a click opens the list, headed 'Working', with the 'i' box", !!list() && list().querySelector("h6").textContent === "Working"
       && !!list().querySelector('button[data-info="work.list"]') && chip().getAttribute("aria-expanded") === "true");
    const info = (w.__INFO || {})["work.list"];
    ok("⭐ 2. the 'i' box's words are the mockup's, word for word (24 by its count), linking to the user guide's entry",
       info && info.text === "Long jobs run one at a time. You can leave the page: the job carries on and this list says when it is done."
       && info.guide === "ug-working-list" && info.text.split(/\s+/).length <= 30
       && fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").includes('id="ug-working-list"'));
    const r0 = rows()[0], r1 = rows()[1];
    ok("⭐ 2. the running row: its line, a thin bar at 33 %, 'Started 14:21' on the reader's clock",
       rows().length === 2 && r0.getAttribute("data-work-row") === "running" && r0.querySelector(".wl-line").textContent === "Route all: 62 of 188 legs"
       && r0.querySelector('[role="progressbar"] i').style.width === "33%" && r0.querySelector("small").textContent === "Started " + w.workClock(T0)
       && /^\d\d:\d\d$/.test(w.workClock(T0)), r0.textContent);
    ok("⭐ 2. Q6: who started it is the row's hover title only, never words on the row",
       r0.getAttribute("title") === "Started by Ada Admin" && !r0.textContent.includes("Ada Admin"));
    ok("2. a running row has no × and no Carry on", !r0.querySelector("[data-work-close]") && !r0.querySelector("[data-work-carry]"));
    await act(async () => { w.workSeen({ id: "j1", state: "running", line: "Route all: 93 of 188 legs", done: 93, total: 188 }); w.workSeen({ id: "nobody", line: "x" }); });
    ok("2. a batch's reply moves the list's row at once (workSeen), in step with the page's own line; a row not in the list is left out",
       rows().length === 2 && rows()[0].querySelector(".wl-line").textContent === "Route all: 93 of 188 legs"
       && rows()[0].querySelector('[role="progressbar"] i').style.width === "49%"
       && (code.match(/workSeen\(j\.working\);/g) || []).length === 4 && code.includes("if(res && res.ok) return res.json();"));
    ok("⭐ 2. the done row: 'R050: Alt 1 made the main route', 'Done 14:02', no bar, a named ×",
       r1.getAttribute("data-work-row") === "done" && r1.querySelector(".wl-line").textContent === "R050: Alt 1 made the main route"
       && r1.querySelector("small").textContent === "Done " + w.workClock(T1) && !r1.querySelector('[role="progressbar"]')
       && r1.querySelector("[data-work-close]").getAttribute("aria-label") === "Close: R050: Alt 1 made the main route"
       && r1.querySelector("[data-work-close]").textContent === "", r1.textContent);
    S.calls.length = 0;
    await click(r1.querySelector("[data-work-close]"));
    ok("⭐ 2. × closes the line on the server (for everyone) and the row goes",
       S.calls.some(c => c.m === "POST" && /\/working\/j2\/close$/.test(c.u) && c.guard === "1") && rows().length === 1 && chip().textContent === "Working · 1");
    await set([STOP]);
    if (!list()) await click(chip());
    const rs = rows()[0];
    ok("⭐ 2. the stopped row: 'Route all stopped at 62 of 188 legs', '14:26 · the routes worked out are kept', Carry on",
       rs.getAttribute("data-work-row") === "stopped" && rs.querySelector(".wl-line").textContent === "Route all stopped at 62 of 188 legs"
       && rs.querySelector("small").textContent === w.workClock(T2) + " · the routes worked out are kept"
       && rs.querySelector("[data-work-carry]").textContent === "Carry on" && !rs.querySelector("[data-work-close]"), rs.textContent);
    await set([{ ...STOP, can_carry: false }]);
    ok("⭐ 2. ...and no Carry on for someone who may not start that job (the server says who may)", rows().length === 1 && !rows()[0].querySelector("[data-work-carry]"));
    // 24 Nov 2026 (axe on the open list in Chrome, the mother session): Escape with the list's own "i" box open leaves
    // the list open (the box's own handler closes the box); Escape then closes the list and the chip has the focus
    const fakePop = w.document.createElement("div"); fakePop.className = "info-pop"; w.document.body.appendChild(fakePop);
    await act(async () => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    ok("⭐ 2. Escape while the list's \"i\" box is open does not close the list under it", !!list());
    fakePop.remove();
    const carryBtn = rows()[0] && rows()[0].querySelector(".wl-line"); if (carryBtn && carryBtn.focus) carryBtn.focus();
    await act(async () => { w.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
    const escClosed = !list();
    ok("⭐ 2. after Escape the chip has the focus (what had it went with the list)", escClosed && w.document.activeElement === chip(),
       String(w.document.activeElement && w.document.activeElement.tagName));
    ok("⭐ 2. the chip names no list it controls (the list is not on the page while closed; axe asked for a review of it)",
       !/aria-controls="work-list"/.test(html) && chip().getAttribute("aria-haspopup") === "dialog" && chip().getAttribute("aria-expanded") === "false");
    await click(chip());
    await act(async () => { w.document.body.dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true })); });
    ok("2. Escape closes the list, and so does a click outside it", escClosed && !list());

    // ------------------------------------------------------------ 3. a row goes to its page
    await set([RUN], {}, "route_all");
    await click(chip());
    ok("3. with no page to go to (this sign-in has not that page) the line is plain words, not a button",
       rows()[0].querySelector(".wl-line").tagName === "SPAN");
    const went = [];
    w.WORK.canGo = (p) => p === "routes"; w.WORK.go = (p) => { went.push(p); return true; };
    await set([RUN, { ...FETCH_STOP, can_carry: false }], {}, "route_all");
    const rb = rows()[0].querySelector(".wl-line");
    ok("⭐ 3. where this sign-in has the page, the line is a button to it; a row for a page it has not stays words",
       rb.tagName === "BUTTON" && rb.getAttribute("data-work-go") === "routes" && rows()[1].querySelector(".wl-line").tagName === "SPAN");
    await click(rb);
    ok("⭐ 3. a click on the row goes to the page the job runs on and closes the list", went.join() === "routes" && !list());

    // ------------------------------------------------------------ 4. Carry on
    await set([STOP]);
    await click(chip());
    let heard = 0; w.addEventListener(w.__WORK_CARRY, () => { heard++; });
    went.length = 0; S.calls.length = 0;
    await click(rows()[0].querySelector("[data-work-carry]"));
    ok("⭐ 4. Carry on on a page-sent job hands the row to its own page: goes there, leaves the row for it, says so",
       went.join() === "routes" && w.WORK.carry && w.WORK.carry.id === "j3" && w.WORK.carry.args.legs === "loaded" && heard === 1
       && !S.calls.some(c => c.m === "POST"), JSON.stringify(w.WORK.carry));
    w.WORK.carry = null;
    w.WORK.canGo = () => true;
    S.refresh = () => reply(200, { started: false, message: "Route all is running. The community places fetch can start when it finishes." });
    await set([FETCH_STOP]);
    await click(chip());
    S.calls.length = 0;
    await click(rows()[0].querySelector("[data-work-carry]"));
    const note = box.querySelector("[data-work-note]");
    ok("⭐ 4. Carry on on a job the server runs starts it again from the list (the community fetch's own call)",
       S.calls.some(c => c.m === "POST" && /\/community\/refresh$/.test(c.u)) && !w.WORK.carry);
    ok("⭐ 4. ...and a refusal is shown as the server's sentence, alone",
       note && note.textContent === "Route all is running. The community places fetch can start when it finishes.", note && note.textContent);
    S.refresh = () => reply(423, { detail: SENT });
    await set([{ ...FETCH_STOP, id: "closures@x", kind: "closures", line: "Road closures: check stopped", page: "lookahead" }]);
    S.calls.length = 0;
    await click(rows()[0].querySelector("[data-work-carry]"));
    ok("4. ...the closures check the same way (its own call; the 423's sentence alone)",
       S.calls.some(c => c.m === "POST" && /forecast-weeks\/restrictions\/refresh$/.test(c.u))
       && box.querySelector("[data-work-note]").textContent === SENT);
    await set([]);

    // ------------------------------------------------------------ 5. Q7: the leave question
    const leave = () => { const ev = new w.Event("beforeunload", { cancelable: true }); w.dispatchEvent(ev); return ev.defaultPrevented; };
    ok("⭐ 5. nothing being sent: closing the tab asks nothing", leave() === false && w.workSending() === false);
    S.start = (body) => reply(200, { ...RUN, id: "j7", line: "Route all: 0 of 188 legs", done: 0, _body: body });
    S.calls.length = 0;
    let job = null;
    await act(async () => { job = await w.workStart("route_all", { profiles: ["A", "B"], legs: "" }); });
    const st = S.calls.find(c => /\/working\/start$/.test(c.u));
    ok("5. a job this page sends starts its row first (POST /api/working/start with the kind and what Carry on needs)",
       job && job.id === "j7" && st && st.m === "POST" && st.body.kind === "route_all" && st.body.profiles.join() === "A,B" && st.guard === "1");
    ok("⭐ 5. while the page is sending the job, closing or reloading the tab raises the browser's own question", leave() === true && w.workSending() === true);
    S.calls.length = 0;
    w.dispatchEvent(new w.Event("pagehide"));
    const gone = S.calls.find(c => /\/working\/j7\/end$/.test(c.u));
    ok("⭐ 5. a tab that does go tells the server at once (a keep-alive request: the row reads 'stopped' without the wait)",
       gone && gone.m === "POST" && gone.keepalive === true && gone.body.state === "stopped" && gone.guard === "1");
    S.calls.length = 0;
    await act(async () => { await w.workEnd(job, "done"); });
    ok("⭐ 5. the job over (its row ended 'done'): the question is not asked any more",
       leave() === false && S.calls.some(c => /\/working\/j7\/end$/.test(c.u) && c.body.state === "done"));
    S.start = () => reply(423, { detail: SENT });
    let refused = null;
    await act(async () => { try { await w.workStart("route_all", {}); } catch (e) { refused = e; } });
    ok("⭐ 5. a start the server refuses arms nothing", refused && leave() === false && w.workSending() === false);
    w.WORK.sending.import = 1;
    const armedImport = leave();
    S.calls.length = 0; w.dispatchEvent(new w.Event("pagehide"));
    delete w.WORK.sending.import;
    ok("5. the Organisation file being sent arms it too (Q8), and is not 'ended' by a closing tab (the server holds its row)",
       armedImport === true && !S.calls.some(c => /\/end$/.test(c.u)) && leave() === false);

    // ------------------------------------------------------------ 6. the refusal's words
    ok("⭐ 6. a 423 gives the server's sentence alone (no 'Not saved.' before it); any other failure gives nothing here",
       w.workBusy(refused) === SENT && w.workBusy({ status: 423, detail: SENT }) === SENT
       && w.workBusy({ status: 500, detail: "x" }) === "" && w.workBusy(new Error("x")) === "" && w.workBusy(null) === "");
    const e423 = await w.errFrom({ status: 423, url: "u", text: () => Promise.resolve(JSON.stringify({ detail: SENT })) });
    ok("6. ...the same from a failed batch reply (errFrom)", w.workBusy(e423) === SENT);
    act(() => { root.unmount(); });
    ok("6. signing out (the chip unmounts) empties the page's copy of the list", w.WORK.jobs.length === 0);
  } else {
    ["1. nothing running: NO chip", "1. 'Working · 1', amber", "1. 'Stopped · 1', red", "1. 'Done · 1', green", "2. the list opens, headed 'Working'",
     "2. the 'i' box's words", "2. the running row", "2. Q6: who started it as the title only", "2. the done row and its ×", "2. the stopped row and Carry on",
     "3. a row goes to its page", "4. Carry on", "5. the leave question only while sending", "6. the refusal alone"].forEach(l => fail.push("⭐ " + l + "  (the page has no Working list)"));
  }

  // ---------------------------------------------------------------- 7. the line where the action was pressed (source)
  const bulk = slice("const bulkBake = async", "const clearRoutes = async");
  const hour = slice("const hourBake = async", "const bulkBake = async");
  const zone = slice("const rebakeAfterZone = async", "const keepMain = async");
  const again = slice("const rebakeRoute = async", "// ---- location add / edit / move / delete ----");
  ok("⭐ 7. the three old shapes are gone from the page (card 2)",
     !code.includes("leg(s) remaining…") && !code.includes("Routing ${vehShort(prof)} —") && !code.includes("Re-routing ${vehShort(prof)} —")
     && !code.includes("this takes a minute; the page will refresh when it finishes") && !code.includes("data-route-busy={r.id}>Routing…")
     && !code.includes("Busy-hour times — ${left} left…") && !code.includes("`Re-routing ${routeId} for "));
  ok("⭐ 7. Route all: starts its row, each batch carries it, the strip shows the row's own line, and it ends done or stopped",
     bulk.includes('job = await workStart("route_all", { profiles: profs, legs: legsNow === "loaded" ? "loaded" : "", carry: c ? c.id : null });')
     && bulk.includes('new URLSearchParams({ profile: prof, limit: "30", job: job.id })') && bulk.includes("setRouteMsg((j.working && j.working.line) || job.line);")
     && bulk.includes('workEnd(job, "done");') && bulk.includes('workEnd(job, "stopped");'));
  ok("7. ...its finished and failed messages are the ones it had, and a refusal is the server's sentence alone",
     bulk.includes("setRouteMsg(`Routing the whole network finished for ${profs.map(vehShort).join(\", \")}. Check the Vehicles column for anything still amber or red.`);")
     && bulk.includes("setRouteMsg(workBusy(e) || `Routing the whole network stopped. ${errMsg(e)} Routes already worked out are kept, so you can run it again.`);"));
  ok("7. ...Carry on runs it with the row's own lorry types and legs and asks no question; a press still asks first",
     bulk.includes("const profs = c ? ((c.args && c.args.profiles) || []) : (rVehicles.length ? rVehicles : [showProfile]);") && bulk.includes("if(!c && !confirm("));
  ok("⭐ 7. Busy-hour times: the same (row, job on each batch, the row's line, done or stopped), its messages kept",
     hour.includes('job = await workStart("hour_times", c ? { carry: c.id }') && hour.includes('new URLSearchParams({ limit: "30", job: job.id })')
     && hour.includes("setRouteMsg((j.working && j.working.line) || job.line);") && hour.includes('workEnd(job, "done");') && hour.includes('workEnd(job, "stopped");')
     && hour.includes("setRouteMsg(workBusy(e) || `Busy-hour times stopped. ${errMsg(e)} Those already worked out are kept.`);")
     && hour.includes("`Busy-hour times worked out for ${p.routes} routes.`"));
  ok("⭐ 7. a zone's re-route: the same on the Zones line, and its end sentence kept",
     zone.includes('job = await workStart("zone_reroute", c ? { profiles: profs, carry: c.id } : { profiles: profs, total: legs.length });')
     && zone.includes('new URLSearchParams({ profile: prof, limit: "30", job: job.id })') && zone.includes("setZoneMsg((j.working && j.working.line) || job.line);")
     && zone.includes('catch(e){ workEnd(job, "stopped"); throw e; }') && zone.includes('workEnd(job, "done");')
     && zone.includes("return ` Re-routed ${done} leg(s) across ${profs.length} vehicle profile(s).`;"));
  ok("⭐ 7. Route again: its row's line on the strip and on the route's own row; stopped if a lorry type failed",
     again.includes('job = await workStart("route_again", { subject: routeId, profiles: profs, via_holding: !!viaHolding, carry: carry ? carry.id : null });')
     && again.includes("const say = (line) => { setRouteMsg(line); setBakeLine(line); };") && again.includes('workEnd(job, failed.length ? "stopped" : "done");')
     && again.includes("`${routeId} re-routed for ${profs.length} vehicle(s).`") && /data-route-busy=\{r\.id\}[^>]*>\{bakeLine\}<\/span>/.test(code)
     && code.includes('if(job) q.set("job", job.id);'));
  ok("7. ...a new or edited route and a moved site bake with no row (they are not in the list)",
     code.includes("await bakeOneRoute(a.id, a.profiles);") && (code.match(/workStart\("route_again"/g) || []).length === 1);
  ok("⭐ 7. the Look-ahead's closures check reads '<its name>: checking' (card 2), and its refusal shows beside its button",
     code.includes('{ttRunning ? `${ttName.split(" (")[0]}: checking`') && code.includes('{ttBusy && !ttRunning && <span role="status" data-work-busy="closures">{ttBusy}</span>}')
     && code.includes("const b = workBusy(e); if(b) setTtBusy(b); else setErr(errSay(\"Couldn't start the road-restriction check.\", e));"));
  ok("⭐ 7. the refusal is shown alone where each second job is pressed: Zones (save, delete), Use Alt 1 as the main route (it read Make primary; John, 25 Nov: "Yes, that name"), a haul road, the Organisation file",
     code.includes('catch(e){ setZoneMsg(workBusy(e) || errSay("Not saved.", e)); }') && code.includes('catch(e){ setZoneMsg(workBusy(e) || errSay("Not deleted.", e)); }')
     && code.includes('const w = workBusy(e) || errSay("Couldn\'t use this alternative.", e);') && code.includes('catch(e){ setMsg(workBusy(e) || errSay("Not done.", e)); }')
     && code.includes('.catch(e => setMsg({ ok: false, text: workBusy(e) || errSay("Not replaced.", e) }))'));
  ok("⭐ 7. card 3: while a job runs the Routing menu's Route all and Busy-hour times are off and the one sentence shows under them, from the server",
     code.includes("disabled={routeBusy || !!work.busy.route_all || !(status && status.length)} data-route-all=\"1\"")
     && code.includes("disabled={routeBusy || !!work.busy.hour_times} data-hour-bake")
     && code.includes('{work.running && <p className="work-busy" role="status" data-work-busy="routes">{work.running === "route_all" ? work.busy.hour_times : work.busy.route_all}</p>}'));
  ok("⭐ 7. ...and Clear all routes is off while ANY long job runs, its refusal the sentence alone (24 Nov 2026)",
     code.includes('onClick={clearRoutes} disabled={routeBusy || !!work.running || !(status && status.length)} data-clear-routes="1"')
     && code.includes('catch(e){ setRouteMsg(workBusy(e) || errSay("Not cleared.", e)); }')
     && !code.includes('disabled={routeBusy || !(status && status.length)} data-clear-routes'));
  ok("⭐ 7. Carry on reaches the page that runs the job: the Data pages pick the row up and run the same action with it",
     code.includes("if(c.kind === \"route_all\") return bulkBake(c);") && code.includes("if(c.kind === \"hour_times\") return hourBake(c);")
     && code.includes("return rebakeRoute(c.subject, all.slice(Math.min(c.done || 0, all.length)), !!(c.args && c.args.via_holding), c);")
     && code.includes("setZoneMsg((await rebakeAfterZone(null, c)).trim());") && code.includes("window.addEventListener(WORK_CARRY, run);"));
  ok("⭐ 7. Q7 at source level: one beforeunload listener for the list, and it does nothing unless the page is sending",
     (code.match(/addEventListener\("beforeunload", workLeave\)/g) || []).length === 1
     && /function workLeave\(ev\)\{\s*if\(!workSending\(\)\) return;\s*ev\.preventDefault\(\); ev\.returnValue = "";/.test(code));
  ok("7. the chip is in the header for staff on the app's pages only, and asks every 4 s while a job runs, every 30 s otherwise, never from a hidden tab",
     code.includes('{role.via !== "reviewer" && view === "portal" && <WorkChip />}') && code.includes("const WORK_POLL_BUSY = 4000, WORK_POLL_IDLE = 30000;")
     && code.includes('if(typeof document !== "undefined" && document.hidden) return next();'));
  ok("7. no Carry on on a phone (nothing on a phone writes)", code.includes("{j.state === \"stopped\" && j.can_carry && !phone && <button"));
  ok("7. the chip's colours: the dark grade on the dark bar, the status tokens on Light's white bar; the list a surface card in every look",
     html.includes(".work-chip.wc-ok{border-color:#047857;background:#0F2A22;color:#6EE7B7;}") && html.includes(".work-chip.wc-bad{border-color:#B91C1C;background:#3B1414;color:#FCA5A5;}")
     && html.includes('html[data-theme="light"] .work-chip{border-color:var(--warn-text);background:var(--st-warn-bg);color:var(--warn-text);}')
     && html.includes(".work-list{position:absolute;right:0;top:40px;z-index:60;width:372px;max-width:calc(100vw - 16px);background:var(--surface);color:var(--ink);"));
  ok("7. the page makes no sentence about a job itself: no job name is joined to 'is running' or 'can start' in the script",
     !/is running\.|are running\.|can start when/.test(code.replace(/\/\/[^\n]*/g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "")));

  console.log(`dom_working_list.js: ${pass} passed, ${fail.length} failed`);
  fail.forEach(f => console.log("  FAIL: " + f));
  process.exit(fail.length ? 1 : 0);
})().catch(e => { console.log("dom_working_list.js: crashed: " + (e && e.stack || e)); console.log(`${pass} passed, ${fail.length + 1} failed`); process.exit(1); });
