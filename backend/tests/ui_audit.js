/*
 * ui_audit.js — the whole app in a REAL browser, every screen × width × look × accent, measured.  16 Oct 2026.
 *
 * ⚠️ NOT PART OF THE DEFAULT SUITE (run_suite.py lists it in BROWSER_ONLY; test_modus.py asserts that). It needs:
 *   - Playwright and axe-core, found through NODE_PATH, and Google Chrome installed — the browser it drives (the user,
 *     17 Oct 2026: "use chrome for all tests"); Playwright's own Chromium only with --browser chromium, or when Chrome
 *     is missing (the report says so):
 *         npm install -g playwright axe-core ; npx playwright install chromium
 *         $env:NODE_PATH = (npm root -g)
 *   - a Python with backend/requirements.txt (the .venv-smoke of this checkout, or of ..\Modus);
 *   - a demo database (backend/forecasts_local.db, or --db). It is COPIED to a temporary folder and the
 *     server runs against the copy, so the database you point it at is never written. The tenant is read from it.
 *
 *     node backend/tests/ui_audit.js                 # quick: 390 and 1366 px, Ink and Dark, + Dark with the Blue accent at 1366, ~15 min
 *     node backend/tests/ui_audit.js --full          # 320 360 390 768 1024 1366 1920 × Ink Light Dark, + the other accents and Dark / Blue at 1920
 *     node backend/tests/ui_audit.js --compare latest    # ...and say what changed since the previous run of the same shape
 *     node backend/tests/ui_audit.js --no-strict-44      # the 44 px rule on a phone back to a warning (decision 14; a failure by default since 18 Oct 2026, see below)
 *     node backend/tests/ui_audit.js --base http://127.0.0.1:8834 --code <planner code> --map-password <pw>
 *     node backend/tests/ui_audit.js --base https://… --email you@… --password …     # a server whose codes are gone (D49)
 *
 * WHAT IT MEASURES (layer 1 of the UI review — the objective part, no judgement)
 *   at every stop (a screen at a width in a look):
 *     - no JavaScript error, no console error, no same-origin 404 / 5xx; a 401 / 403 only on the signed-out screens  (fail)
 *     - no sideways scroll: the document and the portal's own scroller (<main.overflow-auto>)                      (fail)
 *       inner boxes that scroll sideways without a table in them                                                    (warn)
 *     - a page that says it is fixed (the public map, the big screen) does not scroll at all                       (fail)
 *     - axe-core: every violation of a rule tagged WCAG 2.0 / 2.1 / 2.2 A or AA, whatever axe's impact             (fail)
 *       best-practice rules (landmarks, heading order, region)                                                      (warn)
 *       what axe could not decide (text over the map or an image: "incomplete")                                     (warn, axe-needs-review)
 *     - at EVERY width: a visible control whose hit area is under 24 × 24 px and not set apart (WCAG 2.5.8: the hit
 *       area is measured by hit-testing, so a padded ::after counts; the spacing exception and the sentence exception
 *       are applied; axe's own target-size rule is dropped for native checkboxes and radios, which 2.5.8 exempts;
 *       Mapbox GL's attribution and logo are the library's markup and are not measured)                              (fail)
 *       below 768 px, a hit area under 44 × 44 (the platform guides; one under 24 × 24 and crowded is the 24 px failure
 *       above, not listed twice): set apart — its 44 px circle touches no other control, nor the 44 px circle of another
 *       control under 44 (the 24 px rule's spacing test at this rule's size; `spaced: true` on the row) — or inline     (warn)
 *       neither set apart nor inline: a FAILURE (the check targets-44px); --no-strict-44 makes it a warning as before.
 *       Decision 14, 17 Oct 2026: --strict-44 was OFF by default until the phone branch merged (claude/ui-fix-phone, 18 Oct
 *       2026 — decisions 8, 9 and 10: the map's tour dots retired on the phone, the demo bar's pill with its 44 px halo,
 *       the help TOC rows padded to 44 px; with them the password eyes, the sign-in links, the help "top" link and the privacy
 *       Back link); since then it is ON by default. The flag is a grading, not part of the run's shape, so a
 *       strict run pairs with a plain one in --compare.
 *     - the look and accent asked for are the ones on <html>, and the page is the one named (its header)           (fail)
 *       the passes: every look at every width with the Orange accent; the other accents at the widest width in the first
 *       look (--full); and, decision 15 (17 Oct 2026), the Dark look with the Blue accent at the widest width (1366 in the
 *       quick shape, 1920 in --full) — the pair no other pass measures, where white figures on --navy #5B8FF0 fail (3.17:1).
 *       The portal pages only, ~3 min; part of the run's recorded shape (REPORT.options.extraPasses), so --compare pairs
 *       like with like and a run from before it does not pair. Off when --looks or --accents chose the passes by hand.
 *       A control's hit area is ITS OWN (or its label's, for a checkbox / radio): a tap that lands on an ancestor is not
 *       credited — until 17 Oct 2026 it was, so a small control inside a bigger parent (the demo bar's 21 px Guide pill,
 *       centred in a 45 px bar on a phone) passed 44 × 44 on the parent's area and was never a row (finding #33).
 *     - the demo guide's hints as a first visitor sees them (17 Oct 2026, findings #32 / #33), two stops on the phone in the
 *       first look: map-page+guide (the map's tour strip — and NO dot on the phone since decision 8, 18 Oct 2026: the strip's
 *       "Take the tour" carries the tips there, a desk keeps its dots; opened with the signed-in context's cookies — without
 *       them it was the map's password page in every run) and dashboard+guide (the portal's strip and dots, the demo bar's
 *       Guide pill). Each asserts what it is for is on the page (guide-shown; guideDots / guideStrip / guidePill on the
 *       record), so the 24 / 44 px rules measure the dots and the pill — decisions 8 and 9 are verified here.          (fail)
 *     - one h1 on the page (h1-none / h1-many); the two guides are chapters, each an h1, and are exempt from h1-many
 *       (decision 7, 17 Oct 2026 — the recorded design, test_help.py)                                                 (warn)
 *     - text smaller than 12 px (charts' SVG text included), labels cut with an ellipsis, a native confirm()/alert()  (warn)
 *     - a screenshot: the real fold first; when the page or the portal's scroller is taller, the viewport is grown to
 *       the content — the scroller plus what sits above and below it (on a phone the tab bar). Elements sized in vh
 *       (the chart boxes, clamp(200px, 28vh, 420px); the 62vh maps; the 60vh textarea) are pinned at their fold height
 *       first, so they do not inflate with the viewport; then the height is measured again and grown again until it
 *       holds. Max 4,500 px, marked when cut. Never for the map.
 *   once per screen, at the widest width of the run, in the first look (the "deep" stops):
 *     - keyboard: from the top of the page, Tab up to 40 times; every stop must show a visible change (WCAG 2.4.7;
 *       a transparent outline is no outline), be on screen, not be the same element twice in a row (a trap); the
 *       sequence is compared with the document order (WCAG 2.4.3; a jump backwards is a warning)
 *     - the screens behind a click: the Dashboard's folded sections, its two menus, the big screen in its three modes,
 *       the Look-ahead's three views, the Config tabs and a Save, a row's details and the Loads | Tonnes | Lorries switch,
 *       the Users table with the admin token, the public map's presets, collision layer, a route's drawer, share,
 *       export, conditions and Play, and on a phone its sheet, Layers and a route card
 *     - the team (submitter) role, the login user (an invite link → set a password → sign in by email → the portal,
 *       the Users table, a reload while signed in), a wrong password, a dead link, the forgotten-password form
 *     - error and empty states: a read that fails, a search with no match, the app offline, and a tenant with no data
 *       (a second server on an empty database)
 *     - the landing page, the privacy notice, the thanks and error pages
 *   once per run: the time to the public view's first paint, to the portal's first data, each page switch (the
 *   header's title changing), and the largest contentful paint of the first load.
 *   --compare <report.json | latest>: findings new since that run / gone since; screenshots that changed by more than
 *   0.5 % of pixels outside the masked areas (the map canvas, the clock, "updated HH:MM"); a diff image per change.
 *
 * WHAT IT DOES NOT PROVE: nothing about whether a screen is clear, consistent or professional (layer 2, a read of
 * the shots); phones are Chromium's emulation (touch and a coarse pointer below 768 px, no Safari, no real finger);
 * no Lighthouse score (the timings above are what there is); the public map ignores the app's look, so its stops
 * run in the first look only; the map's tiles are Mapbox's real ones (one map load per map stop; --block-mapbox runs
 * the map offline and counts its errors apart); axe's experimental rules for 1.3.4 and 2.5.3 are switched on, the
 * rest of its experimental set is not.
 *
 * OUTPUT  ui-audit/<stamp>/report.json · report.html (the gallery, open in a browser) · summary.md · shots/*.png
 * Count line "N passed, M failed": one assertion per check per stop.
 */
const fs = require("fs");
const os = require("os");
const net = require("net");
const http = require("http");
const path = require("path");
const { spawn, execFileSync } = require("child_process");
const { chromium } = require("playwright");
const AXE_PATH = require.resolve("axe-core/axe.min.js");

const ROOT = path.resolve(__dirname, "..", "..");
const BACKEND = path.join(ROOT, "backend");

// ---------------------------------------------------------------- options --------------------------------------------
function parseArgs(argv) {
  const o = { full: false, headed: false, blockMapbox: false, keepServer: false, guide: false, deep: true, out: path.join(ROOT, "ui-audit"),
              db: path.join(BACKEND, "forecasts_local.db"), python: null, base: null, code: "ui-planner", teamCode: "ui-team-1",
              email: null, password: null, mapPassword: "ui-map", compare: null, widths: null, looks: null, accents: null, pages: null, maxShot: 4500, strict44: true, browser: "chrome" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], v = () => argv[++i];
    if (a === "--full") o.full = true;
    else if (a === "--quick") o.full = false;
    else if (a === "--headed") o.headed = true;
    else if (a === "--block-mapbox") o.blockMapbox = true;
    else if (a === "--keep-server") o.keepServer = true;
    else if (a === "--no-deep") o.deep = false;
    else if (a === "--guide") o.guide = true;
    else if (a === "--strict-44") o.strict44 = true;   // decision 14: the 44 px rule on a phone fails; ON by default since the phone branch (18 Oct 2026)
    else if (a === "--no-strict-44") o.strict44 = false;   // ...the old grading: every 44 px row a warning
    else if (a === "--out") o.out = path.resolve(v());
    else if (a === "--db") o.db = path.resolve(v());
    else if (a === "--python") o.python = v();
    else if (a === "--base") o.base = v().replace(/\/$/, "");
    else if (a === "--code") o.code = v();
    else if (a === "--team-code") o.teamCode = v();
    else if (a === "--email") o.email = v();
    else if (a === "--password") o.password = v();
    else if (a === "--map-password") o.mapPassword = v();
    else if (a === "--compare") o.compare = v();
    else if (a === "--widths") o.widths = v().split(",").map(Number);
    else if (a === "--looks") o.looks = v().split(",");
    else if (a === "--accents") o.accents = v().split(",");
    else if (a === "--pages") o.pages = v().split(",");
    else if (a === "--max-shot") o.maxShot = +v();
    else if (a === "--browser") { o.browser = v(); if (!/^(chrome|chromium)$/.test(o.browser)) { console.error("ui_audit.js: --browser chrome | chromium"); process.exit(2); } }
    else { console.error("ui_audit.js: unknown option " + a); process.exit(2); }
  }
  return o;
}
const OPT = parseArgs(process.argv.slice(2));

// the matrix. Heights are the common device heights at each width (a 320 × 568 small phone — WCAG 1.4.10's width —
// a 390 × 844 phone, a 768 × 1024 tablet, the three laptop / desk sizes); the height decides the fold.
const HEIGHT = { 320: 568, 360: 780, 390: 844, 768: 1024, 1024: 768, 1366: 768, 1920: 1080 };
const WIDTHS = OPT.widths || (OPT.full ? [320, 360, 390, 768, 1024, 1366, 1920] : [390, 1366]);
const LOOKS = OPT.looks || (OPT.full ? ["ink", "light", "dark"] : ["ink", "dark"]);
const EXTRA_ACCENTS = OPT.accents || (OPT.full ? ["blue", "blue-shades", "orange-shades"] : []);
const PORTAL_PAGES = OPT.pages || ["dashboard", "submit", "forecasts", "carbon", "abnormal", "lookahead", "locations", "routes", "zones", "config", "users", "map"];   // 22 Oct 2026: + abnormal (S16 / B5)
const DESK_W = Math.max(...WIDTHS);           // where the deep stops and the keyboard pass run
// decision 15 (17 Oct 2026): one more pass, the Dark look with the Blue accent at the desk width (1366 in the quick shape, 1920
// in --full): the Blue accent's --navy is #5B8FF0 in Dark, where white figures on it fail (3.17:1) — a pair no other pass
// measures (the extra accents run in the first look, Ink). The portal pages only (first = false: no public / sign-in / deep
// stops), ~3 min. Part of the run's shape (sameShape), so a run from before it does not pair in --compare. Off when the looks
// or accents were chosen by hand (--looks / --accents: a custom run says what it wants).
const EXTRA_PASSES = (OPT.looks || OPT.accents) ? [] : [{ look: "dark", accent: "blue", widths: [DESK_W] }];
const PHONE_W = Math.min(...WIDTHS);
const CONFIG_TABS = ["Vehicles", "Materials", "Planning", "Costing · fuel", "Seasonal restrictions", "Map and bulletin", "Everything (JSON)"];
// what the page header says on each portal page (the NAV labels, except Config); the map page has no header
const PAGE_TITLE = { dashboard: "Dashboard", submit: "Submit forecast", forecasts: "Forecasts", carbon: "Carbon planner", abnormal: "Abnormal loads", lookahead: "Look-ahead",
                     locations: "Locations", routes: "Routes", zones: "Zones", config: "Configuration", users: "Users" };
const TEAM_PAGES = ["dashboard", "submit", "forecasts", "carbon", "abnormal", "lookahead", "map"];   // 22 Oct 2026: + abnormal (a team plans its own)
const PHONE_PAGES = ["dashboard", "lookahead", "map"];   // what a phone shows as itself (frontend PHONE_PAGES); the rest is the desk-only card
// the screens a visitor meets signed out: a 401 / 403 there is the gate working, anywhere else it is a defect
const SIGNED_OUT = /^(public|login|login-wrong|login-forgot|login-code|setpw|linkerr|map-password|map-password-wrong|map-public|landing|privacy|thanks|landing-error)$/;
const FIXED_PAGES = /^(map-page|map-public|dashboard-bigscreen|bigscreen-)/;   // pages that must not scroll as a document

// ---------------------------------------------------------------- the server ------------------------------------------
function freePort(start) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once("error", () => resolve(freePort(start + 2)));
    s.listen(start, "127.0.0.1", () => s.close(() => resolve(start)));
  });
}
function findPython() {
  const cands = [OPT.python, path.join(ROOT, ".venv-smoke", "Scripts", "python.exe"), path.join(ROOT, ".venv-smoke", "bin", "python"),
                 path.join(ROOT, "..", "Modus", ".venv-smoke", "Scripts", "python.exe")].filter(Boolean);
  const p = cands.find(c => fs.existsSync(c));
  if (!p) throw new Error("no Python with FastAPI found; pass --python <path to .venv-smoke's python>");
  return p;
}
function httpGet(url) {
  return new Promise((resolve) => {
    const r = http.get(url, (res) => { res.resume(); resolve(res.statusCode); });
    r.on("error", () => resolve(0));
  });
}
function tenantOf(python, dbFile) {
  // the tenant the routes belong to — the server is told the same, so a database under another tenant is not an empty app that passes
  const out = execFileSync(python, ["-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print('\\n'.join(r[0] for r in c.execute('select distinct tenant_id from routes')))", dbFile], { encoding: "utf8" }).trim();
  const ids = out ? out.split(/\r?\n/).filter(Boolean) : [];
  if (ids.length > 1) throw new Error("the database holds routes of more than one tenant: " + ids.join(", "));
  return ids[0] || null;
}
async function startServer(opts) {
  // opts.empty: a server on an EMPTY database (the boots-empty tenant), for the empty-state stops
  if (OPT.base && !opts.empty) return { base: OPT.base, external: true, stop: async () => {} };
  if (!opts.empty && !fs.existsSync(OPT.db)) throw new Error("no database at " + OPT.db + " (pass --db, or copy a demo database to backend/forecasts_local.db)");
  const python = findPython();
  const port = await freePort(opts.empty ? 8850 : 8834);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ui-audit-"));
  const dbCopy = path.join(tmp, "audit.db");
  let tenant = "wolds-link-demo";
  if (!opts.empty) { fs.copyFileSync(OPT.db, dbCopy); tenant = tenantOf(python, dbCopy) || tenant; }
  // the same trick as http_smoke.py: point db at the copy BEFORE main is imported (db has no env var for its path)
  const serve = path.join(tmp, "serve.py");
  fs.writeFileSync(serve, [
    "import sys", `sys.path.insert(0, ${JSON.stringify(BACKEND)})`, "import db", `db._SQLITE_PATH = ${JSON.stringify(dbCopy)}`,
    "import main, uvicorn", `uvicorn.run(main.app, host="127.0.0.1", port=${port}, log_level="warning")`, ""].join("\n"));
  const env = { ...process.env, PYTHONUTF8: "1", ADMIN_TOKEN: "ui-audit-admin-token", PLANNER_CODE: OPT.code, ADMIN_CODE: "ui-admin",
                IPT1_CODE: OPT.teamCode, MAP_PASSWORD: OPT.mapPassword, GATE_SECRET: "ui-audit-gate-secret-local-only",
                TENANT_ID: tenant, APP_URL: `http://127.0.0.1:${port}` };
  // offline for everything that costs: no HERE, no mail, no static-map token. The browser's own Mapbox GL JS still
  // loads the map's tiles with the public token in map/config.js (see --block-mapbox).
  for (const k of ["HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN", "DATABASE_URL", "ALLOW_DEMO_CODES", "MAP_GATE",
                   "SMTP_USER", "SMTP_PASSWORD", "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY"]) delete env[k];
  const proc = spawn(python, [serve], { cwd: BACKEND, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  proc.stdout.on("data", d => { log += d; });
  proc.stderr.on("data", d => { log += d; });
  const base = `http://127.0.0.1:${port}`;
  const t0 = Date.now();
  while (Date.now() - t0 < 90000) {
    if (await httpGet(base + "/api/health") === 200) break;
    if (proc.exitCode != null) throw new Error("the server exited:\n" + log.slice(-2000));
    await new Promise(r => setTimeout(r, 400));
  }
  if (await httpGet(base + "/api/health") !== 200) throw new Error("the server did not answer /api/health in 90 s:\n" + log.slice(-2000));
  const stop = async () => {
    if (OPT.keepServer) { console.log("server kept at " + base + " (database copy " + dbCopy + ")"); return; }
    try { proc.kill(); } catch (e) {}
    await new Promise(r => { const t = setTimeout(() => { try { execFileSync("taskkill", ["/PID", String(proc.pid), "/T", "/F"], { stdio: "ignore" }); } catch (e) {} r(); }, 5000); proc.once("exit", () => { clearTimeout(t); r(); }); });
    for (let i = 0; i < 3; i++) { try { fs.rmSync(tmp, { recursive: true, force: true }); break; } catch (e) { await new Promise(r => setTimeout(r, 500)); } }
  };
  return { base, tenant, log: () => log, stop };
}

// ---------------------------------------------------------------- the report -------------------------------------------
const STAMP = (() => { const d = new Date(), p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`; })();
const RUN_DIR = path.join(OPT.out, STAMP);
if (fs.existsSync(RUN_DIR)) { console.error("ui_audit.js: " + RUN_DIR + " exists already; wait a second"); process.exit(2); }
const SHOTS = path.join(RUN_DIR, "shots");
fs.mkdirSync(SHOTS, { recursive: true });

function gitHead() { try { return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT }).toString().trim(); } catch (e) { return null; } }
const REPORT = { stamp: STAMP, head: gitHead(), options: { full: OPT.full, widths: WIDTHS, looks: LOOKS, extraAccents: EXTRA_ACCENTS, extraPasses: EXTRA_PASSES, pages: PORTAL_PAGES, blockMapbox: OPT.blockMapbox, deep: OPT.deep, guide: OPT.guide, browser: OPT.browser, strict44: OPT.strict44 },
                 stops: [], timings: {}, notes: [], totals: { passed: 0, failed: 0 } };

let PASS = 0;
const FAIL = [];
function ok(label, cond, extra) { if (cond) PASS++; else FAIL.push(label + (extra ? " — " + extra : "")); return !!cond; }
function note(s) { REPORT.notes.push(s); console.log("note: " + s); }

// ---------------------------------------------------------------- the browser-side checks --------------------------
// Runs inside the page. Everything here is plain DOM measurement; nothing is clicked.
function domChecks(arg) {
  const vis = (el) => { if (!el || !(el instanceof Element)) return false; const r = el.getBoundingClientRect(); if (!r.width && !r.height) return false;
    const cs = getComputedStyle(el); if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) return false;
    if (el.closest("details:not([open]) > :not(summary)")) return false; return true; };
  // a control under a sheet or a dialog (the phone's More, the big screen's bar) is not on screen: what is at its centre
  // must be the control itself, something in it, or something it is in
  const hit = (x, y) => document.elementFromPoint(x, y);
  const owns = (el, h) => !!h && (h === el || el.contains(h) || h.contains(el));
  const onTop = (el) => { const r = el.getBoundingClientRect(); const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return true;   // off screen: not covered, just elsewhere
    return owns(el, hit(x, y)); };
  const name = (el) => (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || el.getAttribute("placeholder") || "").trim().replace(/\s+/g, " ").slice(0, 60);
  const sel = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += "#" + el.id; else if (el.className && typeof el.className === "string") s += "." + el.className.trim().split(/\s+/).slice(0, 2).join("."); return s; };
  const doc = document.documentElement;
  // the portal scrolls inside its own <main class="… overflow-auto">, nested in the App's outer <main>: querySelector("main")
  // would answer the OUTER one, whose scroll size is its client size (the 16 Oct review). The scroller, or the last main.
  const mains = [...document.querySelectorAll("main")];
  const main = document.querySelector("main.overflow-auto") || mains[mains.length - 1] || null;
  // a document whose root or body is overflow:hidden cannot be scrolled by a reader, whatever its scrollHeight says
  const rootHidden = /hidden|clip/.test(getComputedStyle(doc).overflowY) || /hidden|clip/.test(getComputedStyle(document.body).overflowY);
  const docScrolls = !rootHidden && doc.scrollHeight > doc.clientHeight + 4;
  const header = document.querySelector('[data-guide="page-header"] h2');
  const out = { vw: innerWidth, vh: innerHeight, theme: doc.getAttribute("data-theme"), accent: doc.getAttribute("data-accent"), title: document.title,
    pageTitle: header ? header.textContent.trim() : null, signedIn: !!document.querySelector('[data-guide="rail"], .phone-tabs'),
    deskOnly: !!document.querySelector("[data-desk-only]"),
    docHScroll: doc.scrollWidth > doc.clientWidth + 1 ? doc.scrollWidth - doc.clientWidth : 0,
    mainHScroll: main && main.scrollWidth > main.clientWidth + 1 ? main.scrollWidth - main.clientWidth : 0,
    docVScroll: docScrolls ? doc.scrollHeight - doc.clientHeight : 0,
    h1: document.querySelectorAll("h1").length, offRight: [], innerScroll: [], tinyTargets: [], smallTargets: [], smallText: [], clipped: [], masks: [] };
  // what pokes out to the right (the cause of a sideways scroll, when there is one), and what extends a fixed page downwards
  if (out.docHScroll || out.mainHScroll) {
    for (const el of document.querySelectorAll("body *")) { const r = el.getBoundingClientRect();
      if (vis(el) && r.right > innerWidth + 1 && r.width < innerWidth * 3 && out.offRight.length < 12) out.offRight.push({ sel: sel(el), right: Math.round(r.right), text: name(el) }); }
  }
  if (arg.fixed && out.docVScroll) {
    // the deepest-reaching elements (a parked sheet or panel counts, even when transformed off screen)
    const deep = [];
    const inScroller = (el) => { let e = el.parentElement; while (e && e !== document.body) { const o = getComputedStyle(e).overflowY; if (o === "auto" || o === "scroll") return true; e = e.parentElement; } return false; };
    for (const el of document.querySelectorAll("body *")) { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      if (cs.display !== "none" && r.bottom > innerHeight + 1 && !el.closest(".mapboxgl-map") && !inScroller(el)) deep.push({ sel: sel(el), bottom: Math.round(r.bottom), top: Math.round(r.top), text: name(el) }); }
    out.offBottom = deep.sort((a, b) => b.bottom - a.bottom).slice(0, 6);
  }
  // boxes that scroll sideways on their own: a table may (1.4.10 allows it); anything else is content hidden off the
  // edge. In either, a control that sits beyond the box's edge is listed (an action nobody sees).
  out.offEdge = [];
  for (const el of document.querySelectorAll("body *")) {
    if (out.innerScroll.length >= 12) break;
    const cs = getComputedStyle(el);
    if ((cs.overflowX === "auto" || cs.overflowX === "scroll") && el.scrollWidth > el.clientWidth + 1 && vis(el) && el !== main && !el.matches(".mapboxgl-map")) {
      const er = el.getBoundingClientRect();
      for (const c of el.querySelectorAll("a[href], button, select, input:not([type=hidden])")) { const r = c.getBoundingClientRect();
        if (r.width && r.left >= er.right - 1 && out.offEdge.length < 12) out.offEdge.push({ sel: sel(c), text: name(c), beyond: Math.round(r.left - er.right), box: sel(el) }); }
      if (!el.querySelector("table") && !el.matches("pre")) out.innerScroll.push({ sel: sel(el), over: el.scrollWidth - el.clientWidth, text: name(el) });
    }
  }
  // targets, at EVERY width (2.5.8 has no viewport condition). The hit area is measured by HIT-TESTING: 12 px (and
  // 22 px) out from the centre must still land on the control, so a small drawing with a padded ::after passes, as
  // on a real pointer. Then 2.5.8's exceptions: a target set 24 px apart from every other (its 24 px circle touches
  // no other target or circle), and a link inside a sentence.
  const q = 'a[href], button, input:not([type="hidden"]), select, textarea, summary, [role="button"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="switch"]';
  const all = [];
  for (const el of document.querySelectorAll(q)) {
    if (!vis(el) || !onTop(el) || el.closest(".mapboxgl-ctrl-attrib, .mapboxgl-ctrl-logo") || el.tabIndex < 0 && !el.matches("a[href], button, input, select, textarea, summary")) continue;
    const r = el.getBoundingClientRect();
    // a checkbox or radio with a label (around it, or <label for>) has the label as its target too
    const labEl = (el.type === "checkbox" || el.type === "radio") ? (el.labels && el.labels[0]) || el.closest("label") : null;
    const lab = labEl ? labEl.getBoundingClientRect() : r;
    const box = { l: Math.min(r.left, lab.left), t: Math.min(r.top, lab.top), r: Math.max(r.right, lab.right), b: Math.max(r.bottom, lab.bottom) };
    // a padded ::before / ::after (the app's .ibtn and .rd-chev: inset −3 px, −11 / −13 px on a coarse pointer) widens the target
    for (const ps of ["::before", "::after"]) { const a = getComputedStyle(el, ps);
      if (a.position === "absolute" && a.content !== "none" && a.content !== "normal") { const n = (v) => { const f = parseFloat(v); return isNaN(f) ? 0 : Math.max(0, -f); };
        box.l -= n(a.left); box.r += n(a.right); box.t -= n(a.top); box.b += n(a.bottom); } }
    const cx = (box.l + box.r) / 2, cy = (box.t + box.b) / 2;
    // what a tap d px out must land on: the control itself (a padded ::before / ::after hit-tests as its element), something
    // in it, or — a checkbox / radio — its label (the label IS its target). NOT an ancestor: until 17 Oct 2026 this used
    // `owns`, which credits one (as onTop must), so a small control inside a bigger parent passed on the parent's area —
    // the demo bar's 21 px Guide pill, centred in a 45 px bar on a phone, passed 44 × 44 and was never a row (finding #33).
    // A tap on the bar beside the pill does nothing.
    const lands = (h) => !!h && (h === el || el.contains(h) || (!!labEl && (h === labEl || labEl.contains(h))));
    const reach = (d) => lands(hit(cx - d, cy)) && lands(hit(cx + d, cy)) && lands(hit(cx, cy - d)) && lands(hit(cx, cy + d));
    const inBox = (d) => box.r - box.l >= 2 * d && box.b - box.t >= 2 * d;
    const has24 = inBox(12) || (cx - 12 >= 0 && cy - 12 >= 0 && cx + 12 <= innerWidth && cy + 12 <= innerHeight && reach(11.5));
    const has44 = inBox(22) || (cx - 22 >= 0 && cy - 22 >= 0 && cx + 22 <= innerWidth && cy + 22 <= innerHeight && reach(21.5));
    // 2.5.8's sentence exception: a link or button inside running text — the nearest block ancestor holds 20+ characters
    // that are not links, or the target is a footnote mark (sup / sub). A wrapped link is as tall as its tallest line box,
    // not its bounding box.
    const par = el.parentElement;
    const block = el.closest("p, li, dd, td, th, figcaption, div, h1, h2, h3, h4, h5, h6, label, section");
    const ownText = block ? [...block.querySelectorAll("a, button")].reduce((n, x) => n + (x.textContent || "").trim().length, 0) : 0;
    const lineH = Math.max(0, ...[...el.getClientRects()].map(r => r.height));
    const pcs = par ? getComputedStyle(par) : null;
    const lh = pcs ? (pcs.lineHeight === "normal" ? parseFloat(pcs.fontSize) * 1.25 : parseFloat(pcs.lineHeight)) : 0;
    const inline = el.matches("a, button") && ((par && /^(SUP|SUB)$/.test(par.tagName))
      || (!!block && getComputedStyle(el).display.startsWith("inline") && (block.textContent || "").trim().length - ownText >= 20 && lineH <= lh + 2));
    all.push({ el, box, w: Math.round(box.r - box.l), h: Math.round(inline ? lineH : box.b - box.t), has24, has44, inline });
  }
  // the spacing test, at the rule's size: does a's circle of radius r (12 for the 24 px rule, 22 for the 44 px rule) touch
  // b's box, or b's circle when b is under that size too? A control it touches nothing with is set apart.
  const circleHits = (a, b, r) => {
    const cx = (a.box.l + a.box.r) / 2, cy = (a.box.t + a.box.b) / 2;
    const nx = Math.max(b.box.l, Math.min(cx, b.box.r)), ny = Math.max(b.box.t, Math.min(cy, b.box.b));
    if (Math.hypot(cx - nx, cy - ny) < r) return true;
    const bx = (b.box.l + b.box.r) / 2, by = (b.box.t + b.box.b) / 2;
    return !(r > 12 ? b.has44 : b.has24) && Math.hypot(cx - bx, cy - by) < 2 * r;
  };
  const crowded = (a, r) => all.some(b => b !== a && circleHits(a, b, r));
  for (const a of all) {
    if (a.inline) continue;   // the sentence exception, for the 24 px rule and the 44 px rule alike
    const row = { sel: sel(a.el), w: a.w, h: a.h, text: name(a.el) };
    if (!a.has24 && crowded(a, 12)) { out.tinyTargets.push(row); continue; }   // the 24 px failure (every width); not listed under 44 as well
    // the 44 px rule on a phone (decision 14, 17 Oct 2026): set apart at 44 (spaced: true — a warning in every mode) or
    // not (a warning; a FAILURE with --strict-44, the check targets-44px)
    if (arg.narrow && !a.has44) out.smallTargets.push(crowded(a, 22) ? row : { ...row, spaced: true });
  }
  // text under 12 px (SVG text — the charts' labels — included), with its contrast against the nearest painted
  // background, smallest first. Not counted: icon glyphs (aria-hidden text, a one-character control that carries an
  // aria-label) and badges (a number of up to three characters in a pill), which are not text anyone reads as text.
  const parseRgb = (s) => { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(s || ""); return m ? [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]] : null; };
  const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = (el) => { let e = el; while (e && e !== document.documentElement) { const c = parseRgb(getComputedStyle(e).backgroundColor); if (c && c[3] >= 0.99) return c; e = e.parentElement; } return [255, 255, 255, 1]; };
  const contrast = (el) => { const fg = parseRgb(getComputedStyle(el).color); if (!fg) return null; const bg = bgOf(el); const a = lum(fg), b = lum(bg); return Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100; };
  const seen = new Set();
  const small = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || !vis(el) || el.closest("script, style, noscript, .mapboxgl-ctrl-attrib, [aria-hidden='true']")) continue;
    const px = parseFloat(getComputedStyle(el).fontSize);
    if (px >= 12) continue;
    const ctl = el.closest("button, a, [role='button']");
    if (t.length <= 1 && ctl && ctl.getAttribute("aria-label")) continue;   // an icon glyph
    const cs = getComputedStyle(el);
    const badge = t.length <= 3 && /^\S+$/.test(t) && parseFloat(cs.borderRadius) >= 6 && el.getBoundingClientRect().width < 40;
    const key = (typeof el.className === "string" ? el.className.trim().split(/\s+/).slice(0, 4).join(".") : el.tagName) + "|" + px + "|" + t.slice(0, 20);
    if (seen.has(key)) continue;
    seen.add(key);
    small.push({ sel: sel(el), px: Math.round(px * 10) / 10, contrast: contrast(el), text: t.slice(0, 50), svg: !!el.closest("svg") || undefined, badge: badge || undefined });
  }
  out.smallText = small.filter(s => !s.badge).sort((a, b) => a.px - b.px).slice(0, 60);
  out.badges = small.filter(s => s.badge).length || undefined;
  // labels the CSS has cut: with an ellipsis, or clipped with none (overflow hidden and the text wider than its box);
  // and an inline label broken over two lines with no space in it (a kbd, a code)
  for (const el of document.querySelectorAll("*")) {
    if (out.clipped.length >= 30) break;
    const cs = getComputedStyle(el);
    if (!vis(el) || el.childElementCount !== 0 || el.closest("svg, script, style")) continue;
    if ((cs.overflowX !== "visible") && el.scrollWidth > el.clientWidth + 1 && (cs.textOverflow === "ellipsis" || cs.overflowX === "hidden" || cs.overflowX === "clip"))
      out.clipped.push({ sel: sel(el), text: name(el), over: el.scrollWidth - el.clientWidth, noEllipsis: cs.textOverflow !== "ellipsis" || undefined });
    else if (cs.display.startsWith("inline") && !/\s/.test((el.textContent || "").trim()) && (el.textContent || "").trim().length > 1 && el.getClientRects().length > 1)
      out.clipped.push({ sel: sel(el), text: name(el), wrapped: true });
  }
  // the demo guide's hints, counted at the same instant as the targets (the guide stops assert them, 17 Oct 2026): the map's
  // (#guide-strip) or the app's (.guide-strip) tour strip, the dots, and the demo bar's Guide pill
  out.guide = { dots: [...document.querySelectorAll(".guide-dot")].filter(vis).length, strip: [...document.querySelectorAll(".guide-strip, #guide-strip")].filter(vis).length,
                pill: [...document.querySelectorAll("button.demo-bar-guide")].filter(vis).length };
  // what the compare must ignore: the map's canvas, the clock, "updated HH:MM" — they change every run
  for (const el of document.querySelectorAll(".mapboxgl-canvas, .dash-clock, canvas")) { const r = el.getBoundingClientRect(); if (r.width && r.height) out.masks.push([Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]); }
  for (const el of document.querySelectorAll("span, div, time")) { if (el.childElementCount === 0 && /\bupdated \d\d:\d\d\b|^\d\d:\d\d$/.test(el.textContent.trim())) { const r = el.getBoundingClientRect(); if (r.width) out.masks.push([Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]); } }
  const nav = performance.getEntriesByType("navigation")[0];
  if (nav) out.nav = { dcl: Math.round(nav.domContentLoadedEventEnd), load: Math.round(nav.loadEventEnd), lcp: window.__uiAuditLCP ? Math.round(window.__uiAuditLCP) : null };
  return out;
}

async function runAxe(page) {
  const has = await page.evaluate(() => !!window.axe).catch(() => false);
  if (!has) await page.addScriptTag({ path: AXE_PATH });
  // Mapbox GL's attribution list (.mapboxgl-ctrl-attrib) is left out: its markup is the library's and axe faults it on
  // every map; the zoom buttons stay in. Two experimental rules are on (1.3.4 orientation, 2.5.3 label in name).
  const res = await page.evaluate(async () => {
    const r = await window.axe.run({ include: [["html"]], exclude: [[".mapboxgl-ctrl-attrib"]] }, { iframes: false, resultTypes: ["violations", "incomplete"],
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
      rules: { "css-orientation-lock": { enabled: true }, "label-content-name-mismatch": { enabled: true } } });
    // up to 20 nodes a rule; colour-contrast nodes worst first (the ratio parsed from axe's message), so a cap never hides the worst
    const ratio = (n) => { const m = /contrast of ([\d.]+)/.exec(n.why); return m ? +m[1] : 99; };
    const pick = (v) => { const nodes = v.nodes.map(n => ({ target: n.target.join(" "), html: n.html.slice(0, 140), why: (n.any[0] || n.all[0] || n.none[0] || {}).message || "" }));
      if (v.id === "color-contrast") nodes.sort((a, b) => ratio(a) - ratio(b));
      return { id: v.id, impact: v.impact, help: v.help, tags: v.tags.filter(t => /^wcag|best-practice|experimental/.test(t)), nodes: nodes.slice(0, 20), count: v.nodes.length }; };
    // Mapbox's logo and bottom controls are the library's too (their region / landmark rows say nothing about the app)
    const mine = (v) => { v.nodes = v.nodes.filter(n => !/\.mapboxgl-ctrl-(logo|bottom)/.test(n.target)); v.count = Math.min(v.count, v.nodes.length || v.count); return v; };
    return { violations: r.violations.map(pick).map(mine).filter(v => v.nodes.length), incomplete: r.incomplete.map(pick).map(mine).filter(v => v.nodes.length) };
  });
  // 2.5.8 exempts a target whose size the user agent decides (a native checkbox or radio the author did not size), and
  // the pointer target of one inside a <label> is the label: axe's target-size credits neither, this harness's own check does
  for (const v of res.violations) if (v.id === "target-size") {
    v.nodes = v.nodes.filter(n => !/^<input[^>]*type="(checkbox|radio)"/.test(n.html));
    v.count = v.nodes.length;
  }
  res.violations = res.violations.filter(v => v.count > 0);
  return res;
}

// ---------------------------------------------------------------- settle, screenshot --------------------------------
function newStore() { return { errors: [], http: [], failed: [], dialogs: [], inflight: 0, open: [], settleWhy: "" }; }
function watch(page, store) {
  // everything the page says or fails on, drained per stop
  // a film or a sound streams for as long as it plays: not something to wait for
  const counts = (r) => r.resourceType() !== "media";
  const done = (r) => { if (!counts(r)) return; store.inflight = Math.max(0, store.inflight - 1); const i = store.open.indexOf(r.url().slice(0, 100)); if (i >= 0) store.open.splice(i, 1); };
  page.on("request", r => { if (!counts(r)) return; store.inflight++; store.open.push(r.url().slice(0, 100)); });
  page.on("requestfinished", done);
  page.on("requestfailed", r => { done(r);
    // a request the page itself cancelled (a map re-layout drops its font fetches, a navigation drops the rest) is not a failure
    const why = (r.failure() || {}).errorText || ""; if (!/ERR_ABORTED/.test(why)) store.failed.push(r.url().slice(0, 160) + " " + why); });
  page.on("framenavigated", f => { if (f === page.mainFrame()) { store.inflight = 0; store.open.length = 0; } });
  page.on("pageerror", e => store.errors.push("pageerror: " + String(e.message || e).slice(0, 300)));
  page.on("console", m => { if (m.type() === "error") store.errors.push("console: " + m.text().slice(0, 300)); });
  page.on("response", r => { const s = r.status(); if (s >= 400) store.http.push({ status: s, url: r.url().slice(0, 160) }); });
  // the app's confirmations are native confirm() boxes: outside every look, axe and the screenshot. Dismissed, and noted.
  page.on("dialog", d => { store.dialogs.push(d.type() + ": " + d.message().slice(0, 120)); d.dismiss().catch(() => {}); });
}
function drain(store) { return { errors: store.errors.splice(0), http: store.http.splice(0), failed: store.failed.splice(0), dialogs: store.dialogs.splice(0) }; }
const LOADING = /^(Loading\b.*…|Signing you back in…|Checking your link…|Preparing…|Making the bulletin…|Saving…|Checking…|Sending…)$/;
async function settle(page, store, quiet = 700, cap = 15000) {
  // quiet = no request in flight and nothing saying "Loading…" for `quiet` ms. A stop that never gets there is measured
  // anyway after `cap` and says why (a not-settled warning), so a page that keeps a request open is visible in the report.
  const t0 = Date.now();
  let quietSince = null, lastWhy = "";
  while (Date.now() - t0 < cap) {
    const busy = await page.evaluate((re) => {
      const shown = (el) => { const r = el.getBoundingClientRect(); return (r.width || r.height) && !el.closest("details:not([open]) > :not(summary)"); };
      const ab = [...document.querySelectorAll('[aria-busy="true"]')].find(shown);
      if (ab) return "aria-busy";
      const rx = new RegExp(re);
      // a folded section's own "Loading…" (the CLP figures, read on first open) is not the page loading
      for (const el of document.querySelectorAll("div, td, span, p, button")) {
        if (el.childElementCount === 0 && rx.test(el.textContent.trim()) && shown(el)) return "loading: " + el.textContent.trim();
      }
      return "";
    }, LOADING.source).catch(() => "");
    const why = busy || (store.inflight ? `${store.inflight} request(s) open: ${store.open.slice(0, 2).join(", ")}` : "");
    if (why) lastWhy = why;
    if (!why) { if (quietSince == null) quietSince = Date.now(); else if (Date.now() - quietSince >= quiet) { store.settleWhy = ""; break; } }
    else quietSince = null;
    await page.waitForTimeout(120);
    if (Date.now() - t0 >= cap) store.settleWhy = `never quiet for ${quiet} ms in ${cap} ms; last seen: ${lastWhy || "short requests back to back"}`;
  }
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))).catch(() => {});
  return Date.now() - t0;
}
// how tall the viewport must be to show the whole page (0 when nothing scrolls). Runs inside the page. The portal's
// own scroller (<main.overflow-auto>, else the last <main>) when it scrolls: its content plus what sits ABOVE it (the
// header, the demo bar) and BELOW it — on a phone the tab bar, .phone-tabs, a flex sibling under the scroller; left
// out of the sum until 17 Oct, every phone shot lost its last ~57 px under the bar. Else a document that scrolls: its
// scrollHeight. A root or body that is overflow:hidden cannot be scrolled by a reader, whatever its scrollHeight says.
function contentHeight() {
  const doc = document.documentElement;
  const mains = [...document.querySelectorAll("main")];
  const main = document.querySelector("main.overflow-auto") || mains[mains.length - 1] || null;
  if (main && main.scrollHeight > main.clientHeight + 4) {
    const r = main.getBoundingClientRect();
    return Math.ceil(main.scrollHeight + r.top + Math.max(0, innerHeight - r.bottom));
  }
  const rootHidden = /hidden|clip/.test(getComputedStyle(doc).overflowY) || /hidden|clip/.test(getComputedStyle(document.body).overflowY);
  return !rootHidden && doc.scrollHeight > doc.clientHeight + 4 ? doc.scrollHeight : 0;
}
// an element whose height follows the viewport — vh in a rule's height / min-height / max-height (the chart boxes,
// clamp(200px, 28vh, 420px); Tailwind's h-[60vh], max-h-[72vh]) or in its inline style (the 62vh maps) — keeps the
// size it has at the fold while the viewport is grown. Else a grown shot shows them taller than any screen draws them
// and the end of the page falls below the height measured at the fold (17 Oct: the 390 px Dashboard, 3,968 px tall,
// had lost its last gate rows and the Gate by gate expander this way; at 1366 the charts grew from 215 to 420 px).
// Runs inside the page; returns how many were pinned. unpinViewportUnits() puts their inline styles back.
function pinViewportUnits() {
  const sels = [];
  // a rule's own style first, then what it nests: a plain style rule has a (usually empty) cssRules list of its own
  const walk = (rules) => { for (const r of rules) {
    if (r.style && r.selectorText && /\d(vh|svh|dvh|lvh)\b/.test(r.style.height + " " + r.style.minHeight + " " + r.style.maxHeight)) sels.push(r.selectorText);
    if (r.cssRules && r.cssRules.length) walk(r.cssRules); } };
  for (const ss of document.styleSheets) { try { walk(ss.cssRules); } catch (e) {} }   // a cross-origin sheet (Mapbox's) cannot be read: skipped
  const els = new Set();
  for (const s of sels) { try { document.querySelectorAll(s).forEach(e => els.add(e)); } catch (e) {} }
  for (const e of document.querySelectorAll("[style*='vh']")) els.add(e);
  let n = 0;
  for (const el of els) {
    if (el === document.documentElement || el === document.body) continue;
    const h = el.getBoundingClientRect().height; if (!h) continue;   // hidden: nothing to pin
    el.setAttribute("data-ui-audit-style", el.getAttribute("style") || "");
    el.style.setProperty("height", h + "px", "important"); el.style.setProperty("min-height", "0", "important"); el.style.setProperty("max-height", "none", "important");
    n++;
  }
  return n;
}
function unpinViewportUnits() {
  for (const el of document.querySelectorAll("[data-ui-audit-style]")) { const s = el.getAttribute("data-ui-audit-style"); if (s) el.setAttribute("style", s); else el.removeAttribute("style"); el.removeAttribute("data-ui-audit-style"); }
}
async function shoot(page, file, width, height, contentH, fixed) {
  // the real fold first; a page or a portal scroller taller than the viewport is pictured whole by growing the viewport
  // (never a fixed page: the map re-tiles to the new size and shows a screen no phone shows). A fullscreen window
  // (the big screen) cannot be resized, and is shot as it is. Before growing, what is sized in vh is pinned at its
  // fold height (pinViewportUnits); once grown, the content can still grow — a panel that draws late — so the height
  // is measured again and the viewport grown again until it holds.
  const full = await page.evaluate(() => !!document.fullscreenElement).catch(() => false);
  let want = (!fixed && !full && contentH > height + 4) ? Math.min(Math.ceil(contentH), OPT.maxShot) : height;
  let truncated = !fixed && contentH > OPT.maxShot, regrown = 0, pinned = 0;
  if (want > height) {
    pinned = await page.evaluate(pinViewportUnits).catch(() => 0);
    await page.setViewportSize({ width, height: want }); await page.waitForTimeout(150);
    for (let i = 0; i < 4 && want < OPT.maxShot; i++) {
      await page.waitForTimeout(250);
      const again = await page.evaluate(contentHeight).catch(() => 0);
      if (again <= want + 4) break;
      if (again > OPT.maxShot) truncated = true;
      want = regrown = Math.min(Math.ceil(again), OPT.maxShot);
      await page.setViewportSize({ width, height: want }); await page.waitForTimeout(150);
    }
  }
  await page.screenshot({ path: file, fullPage: false });
  if (want > height) { await page.setViewportSize({ width, height }); await page.evaluate(unpinViewportUnits).catch(() => {}); await page.waitForTimeout(100); }
  return { grown: want > height ? want : 0, regrown, truncated, pinned };
}
async function leaveFullscreen(page) {
  await page.evaluate(() => document.fullscreenElement && document.exitFullscreen && document.exitFullscreen()).catch(() => {});
  await page.waitForTimeout(300);
}

// ---------------------------------------------------------------- one stop -------------------------------------------
const ALLOWED_CONSOLE = [
  /cdn\.tailwindcss\.com/,                                 // Tailwind's "not for production" note is a warning on some builds, an error on others
  /\[BABEL\] Note: The code generator has deoptimised/,   // Babel standalone on a >500 KB script: a note about ITS output's styling, printed as an error
];
const WCAG = (v) => v.tags.some(t => /^wcag2(1|2)?a{1,2}$/.test(t));

async function audit(page, store, meta) {
  const fixed = FIXED_PAGES.test(meta.name) || !!meta.fixed;
  const t = await settle(page, store);
  const dom = await page.evaluate(domChecks, { narrow: meta.width < 768, fixed });
  dom.contentH = await page.evaluate(contentHeight).catch(() => 0);
  const axe = await runAxe(page);
  const drained = drain(store);
  const file = `${meta.name}__${meta.width}__${meta.look}__${meta.accent}.png`.replace(/[^A-Za-z0-9_.+-]/g, "-");
  const shot = await shoot(page, path.join(SHOTS, file), meta.width, meta.height, dom.contentH, fixed);
  // a 401 / 403 is the gate working on the signed-out screens, and on the Users page opened with a CODE (it asks for
  // the admin token first: the list answers 403 until it is typed — by design, G3)
  const signedOut = SIGNED_OUT.test(meta.name) || (meta.page === "users" && !OPT.email && !/login-user/.test(meta.name));
  // a stop whose premise is a request the harness CUT (meta.cut: the read it aborted, or every request while the context
  // is offline): the browser's own "Failed to load resource" line for it and the request itself are the premise, not a
  // defect — a pageerror (the app not coping) still counts
  const cut = meta.cut || null;
  // a dead link (the linkerr stop): /api/auth/check answers 410 Gone by design (G3) — the premise, as 401 / 403 are above
  const gone = meta.expectGone || null;
  const errors = drained.errors.filter(e => !ALLOWED_CONSOLE.some(re => re.test(e)) && !(signedOut && /status of (401|403)/.test(e))
    && !(cut && /^console: Failed to load resource: net::ERR_(FAILED|INTERNET_DISCONNECTED|ABORTED)/.test(e))
    && !(gone && /status of 410 \(Gone\)/.test(e)));
  const failedReqs = cut ? drained.failed.filter(f => !cut.test(f.split(" ")[0])) : drained.failed;   // the entry is "url reason"
  const mapboxErr = OPT.blockMapbox ? errors.filter(e => /mapbox|tile|style|glyph|sprite/i.test(e)) : [];
  const realErr = errors.filter(e => !mapboxErr.includes(e));
  const http = drained.http.filter(h => !(signedOut && (h.status === 401 || h.status === 403)) && !(gone && h.status === 410 && gone.test(h.url)));
  const sameOrigin = http.filter(h => h.url.startsWith(meta.base));
  const third = http.filter(h => !h.url.startsWith(meta.base) && !(OPT.blockMapbox && /mapbox/.test(h.url)));
  const axeFail = axe.violations.filter(WCAG);
  const axeWarn = axe.violations.filter(v => !WCAG(v));
  const label = `${meta.name} @${meta.width} ${meta.look}/${meta.accent}`;
  const checks = [
    { id: "no-js-errors", ok: realErr.length === 0, detail: realErr },
    { id: "no-http-errors", ok: sameOrigin.length === 0, detail: sameOrigin },
    { id: "no-sideways-scroll", ok: !dom.docHScroll && !dom.mainHScroll, detail: dom.docHScroll || dom.mainHScroll ? { doc: dom.docHScroll, main: dom.mainHScroll, offRight: dom.offRight } : null },
    { id: "axe-wcag", ok: axeFail.length === 0, detail: axeFail },
    { id: "targets-24px", ok: dom.tinyTargets.length === 0, detail: dom.tinyTargets },
  ];
  if (meta.portal) {
    checks.push({ id: "look-applied", ok: dom.theme === meta.look && dom.accent === meta.accent, detail: { theme: dom.theme, accent: dom.accent } });
    // the page named is the one on screen: its header's title — or, on a phone, the desk-only card for a page made for a desk (D9)
    const want = PAGE_TITLE[meta.page];
    const deskCard = meta.width < 768 && !PHONE_PAGES.includes(meta.page) && dom.deskOnly;
    if (want) checks.push({ id: "page-is", ok: dom.signedIn && (dom.pageTitle === want || deskCard), detail: { header: dom.pageTitle, deskOnly: dom.deskOnly, signedIn: dom.signedIn } });
    else checks.push({ id: "page-is", ok: dom.signedIn, detail: { signedIn: dom.signedIn } });
  }
  if (fixed) checks.push({ id: "no-page-scroll", ok: !dom.docVScroll, detail: dom.docVScroll ? { by: dom.docVScroll, offBottom: dom.offBottom } : null });
  if (meta.mapState) checks.push({ id: "map-loaded", ok: meta.mapState === "loaded", detail: meta.mapState });
  // the guide stops (meta.guide, 17 Oct 2026 — findings #32 and #33): what the stop is FOR must be on the page, else it fails —
  // the map's tour strip ("map": map-page+guide) with its dots at a desk and NONE below 768 px (decision 8, 18 Oct 2026: the
  // map draws no dot on a phone — a dot there is the failure now), the demo bar's Guide pill ("portal": dashboard+guide).
  // The counts go on the record (guideDots, guideStrip, guidePill), so a run says what the 24 / 44 px rules had to measure.
  const mapGuideOk = dom.guide.strip > 0 && (meta.width < 768 ? dom.guide.dots === 0 : dom.guide.dots > 0);
  if (meta.guide) checks.push({ id: "guide-shown", ok: meta.guide === "map" ? mapGuideOk : dom.guide.pill > 0, detail: dom.guide });
  // the 44 px rule on a phone (decision 14): with --strict-44 a control under 44 × 44 that is neither inline nor set apart
  // FAILS (the check targets-44px); the set-apart rows (spaced: true) stay a warning; without the flag every row is a warning
  const small44 = meta.width < 768 ? dom.smallTargets : [];
  const strict44 = OPT.strict44 ? small44.filter(r => !r.spaced) : [];
  if (OPT.strict44 && meta.width < 768) checks.push({ id: "targets-44px", ok: strict44.length === 0, detail: strict44 });
  const warn44 = OPT.strict44 ? small44.filter(r => r.spaced) : small44;
  const warnings = [];
  if (axeWarn.length) warnings.push({ id: "axe-minor", detail: axeWarn });
  if (axe.incomplete.length) warnings.push({ id: "axe-needs-review", detail: axe.incomplete });
  if (warn44.length) warnings.push({ id: "targets-44px", detail: warn44 });
  if (dom.smallText.length) warnings.push({ id: "text-under-12px", detail: dom.smallText });
  if (dom.clipped.length) warnings.push({ id: "text-clipped", detail: dom.clipped });
  if (dom.innerScroll.length) warnings.push({ id: "inner-sideways", detail: dom.innerScroll });
  if (dom.offEdge && dom.offEdge.length) warnings.push({ id: "controls-off-edge", detail: dom.offEdge });
  if (dom.badges) warnings.push({ id: "badges-under-12px", detail: dom.badges });
  if (third.length) warnings.push({ id: "third-party-http", detail: third });
  if (failedReqs.length) warnings.push({ id: "requests-failed", detail: failedReqs });
  if (drained.dialogs.length) warnings.push({ id: "native-dialog", detail: drained.dialogs });
  if (mapboxErr.length) warnings.push({ id: "mapbox-offline", detail: mapboxErr });
  // the two guides are chapters, each an h1 — a recorded design (test_help.py), exempt from h1-many by decision 7 (17 Oct 2026); a shell whose content is an iframe has the map's h1 in the map's stop
  if (dom.h1 === 0 && !/^(public|map)$/.test(meta.name)) warnings.push({ id: "h1-none", detail: 0 });
  else if (dom.h1 > 1 && !/^help/.test(meta.name)) warnings.push({ id: "h1-many", detail: dom.h1 });
  if (store.settleWhy) warnings.push({ id: "not-settled", detail: store.settleWhy });
  if (shot.truncated) warnings.push({ id: "shot-truncated", detail: { contentH: dom.contentH, maxShot: OPT.maxShot } });
  for (const c of checks) ok(`${label}: ${c.id}`, c.ok, c.ok ? "" : JSON.stringify(c.detail).slice(0, 300));
  const stop = { ...meta, shot: "shots/" + file, shotGrown: shot.grown || undefined, shotRegrown: shot.regrown || undefined, shotPinned: shot.pinned || undefined, settleMs: t, settleWhy: store.settleWhy || undefined, checks, warnings,
                 theme: dom.theme, accentApplied: dom.accent, title: dom.title, pageTitle: dom.pageTitle, contentH: dom.contentH, nav: dom.nav, masks: dom.masks };
  delete stop.base;
  if (meta.guide) { stop.guideDots = dom.guide.dots; stop.guideStrip = dom.guide.strip; stop.guidePill = dom.guide.pill ? "button.demo-bar-guide" : null; }
  if (cut) stop.cut = cut.source;   // on the record as text (a RegExp would serialise as {})
  if (gone) stop.expectGone = gone.source;
  REPORT.stops.push(stop);
  const bad = checks.filter(c => !c.ok).map(c => c.id);
  process.stdout.write(`${bad.length ? "FAIL" : "ok  "} ${label.padEnd(46)} ${String(t).padStart(5)} ms  ${bad.join(" ")}${warnings.length ? "  (" + warnings.map(w => w.id).join(" ") + ")" : ""}\n`);
  return stop;
}

// the keyboard pass: from the top of the page, Tab up to 40 times; each stop must be visible and must show it has the focus
async function keyboardPass(page, meta) {
  // no smooth scroll (the rect would be read mid-glide) and no transitions (a ring that fades in would be read before it lands)
  await page.addStyleTag({ content: "html{scroll-behavior:auto !important} *, *::before, *::after{transition:none !important; animation-duration:0s !important}" }).catch(() => {});
  const CAP = meta.portal === false || /^(help|bulletin|landing|privacy|thanks)/.test(meta.name) ? 120 : 40;   // a document: to the end
  // the sequential-focus starting point: a sentinel at the very start of <body>, focused and removed (blur() does not move it)
  await page.evaluate(() => {
    document.querySelectorAll("[data-ui-audit-seen]").forEach(e => e.removeAttribute("data-ui-audit-seen"));
    const s = document.createElement("span"); s.tabIndex = -1; document.body.prepend(s); s.focus(); s.remove();
    const m = document.querySelector("main.overflow-auto"); if (m) m.scrollTop = 0; window.scrollTo(0, 0);
  });
  const stops = [];
  let prevKey = null, stuck = 0;
  for (let i = 0; i < CAP; i++) {
    await page.keyboard.press("Tab");
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))).catch(() => {});
    const info = await page.evaluate((n) => {
      const el = document.activeElement;
      if (!el || el === document.body) return { body: true };
      const seenBefore = el.hasAttribute("data-ui-audit-seen");
      el.setAttribute("data-ui-audit-seen", String(n));
      const read = (e, ps) => { const cs = getComputedStyle(e, ps || null);
        const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0 && !/rgba\(\d+, \d+, \d+, 0\)|transparent/.test(cs.outlineColor) ? cs.outlineStyle + cs.outlineWidth + cs.outlineColor : "none";
        return [outline, cs.boxShadow, cs.backgroundColor, cs.borderColor, cs.color, cs.textDecorationLine].join("|"); };
      const par = el.parentElement;
      const all3 = (e) => read(e) + read(e, "::before") + read(e, "::after");   // a ring drawn by a pseudo-element counts
      const focused = all3(el) + (par ? "/" + read(par) : "");
      const r = el.getBoundingClientRect();
      const inView = r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
      el.blur(); const blurred = all3(el) + (par ? "/" + read(par) : ""); el.focus({ preventScroll: true });
      const nm = (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || el.getAttribute("placeholder") || el.value || "").trim().replace(/\s+/g, " ").slice(0, 50);
      // document order, for 2.4.3: where this stop sits among every focusable element
      const all = [...document.querySelectorAll('a[href], button, input:not([type="hidden"]), select, textarea, summary, iframe, [tabindex]:not([tabindex="-1"])')];
      const row = { key: n, tag: el.tagName.toLowerCase(), text: nm, inView, visibleFocus: focused !== blurred, seenBefore, order: all.indexOf(el), w: Math.round(r.width), h: Math.round(r.height) };
      if (!row.visibleFocus) row.styles = { focused, blurred };   // what was compared, so a reader can see what the control does and does not change
      return row;
    }, i).catch(() => null);
    if (!info || info.body) { stops.push({ tag: "(body)", text: "", inView: true, visibleFocus: true, skipped: true, order: -1 }); break; }   // the page's stops are exhausted
    // a frame or a media player keeps the focus for several Tabs (its own controls): not a trap, and not this document
    const opaque = /^(iframe|video|audio|embed|object)$/.test(info.tag);
    if (info.seenBefore) { if (opaque) { if (info.tag === "iframe") break; continue; }
      if (prevKey !== null && stops.length && stops[stops.length - 1].order === info.order) { stuck++; stops[stops.length - 1].stuck = true; if (stuck >= 2) break; else continue; } break; }   // wrapped round, or stuck
    prevKey = info.key;
    if (opaque) { info.skipped = true; info.visibleFocus = true; }
    stops.push(info);
  }
  const real = stops.filter(s => !s.skipped && s.w > 0 && s.h > 0);
  const noRing = real.filter(s => !s.visibleFocus);
  const hidden = real.filter(s => !s.inView);
  const trapped = stops.filter(s => s.stuck);
  const reached = real.length + stops.filter(s => s.tag === "iframe").length;
  const back = real.filter((s, i) => i > 0 && s.order >= 0 && real[i - 1].order >= 0 && s.order < real[i - 1].order);   // a jump backwards in document order
  const label = `${meta.name} @${meta.width} ${meta.look}: keyboard`;
  ok(`${label} — every tab stop shows its focus`, noRing.length === 0, noRing.map(s => `${s.tag} "${s.text}"`).join("; ").slice(0, 300));
  ok(`${label} — every tab stop is on screen`, hidden.length === 0, hidden.map(s => `${s.tag} "${s.text}"`).join("; ").slice(0, 300));
  ok(`${label} — the focus never sticks`, trapped.length === 0, trapped.map(s => `${s.tag} "${s.text}"`).join("; ").slice(0, 300));
  ok(`${label} — something takes the focus`, reached > 0);
  const warnings = [];
  if (back.length) warnings.push({ id: "focus-order", detail: back.map(s => `${s.tag} "${s.text}" (document position ${s.order})`) });
  REPORT.stops.push({ name: meta.name + "+keyboard", width: meta.width, height: meta.height, look: meta.look, accent: meta.accent, kind: "keyboard", stops, checks: [
    { id: "focus-visible", ok: noRing.length === 0, detail: noRing }, { id: "focus-on-screen", ok: hidden.length === 0, detail: hidden },
    { id: "focus-not-stuck", ok: trapped.length === 0, detail: trapped }, { id: "focus-reaches", ok: reached > 0, detail: reached }], warnings });
  process.stdout.write(`${noRing.length || hidden.length || trapped.length ? "FAIL" : "ok  "} ${label.padEnd(46)}  ${real.length} stops${noRing.length ? ", " + noRing.length + " without a visible focus" : ""}${hidden.length ? ", " + hidden.length + " off screen" : ""}${trapped.length ? ", stuck" : ""}${back.length ? ", " + back.length + " out of order" : ""}\n`);
}

// ---------------------------------------------------------------- contexts, sign-in ----------------------------------
async function newContext(browser, look, accent, width, guide) {
  // one context per width: a phone (below 768 px) is a touch device with a coarse pointer, which the app's CSS reads
  const ctx = await browser.newContext({ viewport: { width, height: HEIGHT[width] || 800 }, deviceScaleFactor: 1, locale: "en-GB", timezoneId: "Europe/London",
    colorScheme: look === "dark" ? "dark" : "light", isMobile: width < 768, hasTouch: width < 768 });
  // the remembered look and accent, read by the <head> script before anything draws (W16); the demo guide's strip and
  // dots and the map's own tour switched off (what "Hide the tips" writes) — the keyboard pass would otherwise measure
  // the tour's bubble, not the page. --guide (or the map-page+guide stop) keeps them, as a first visitor sees them.
  // And an LCP observer.
  await ctx.addInitScript(([l, a, g]) => {
    try { localStorage.setItem("modus_theme", l); localStorage.setItem("modus_accent", a); if (!g) { localStorage.setItem("wayscope_guide_all", "off"); localStorage.setItem("wayscope_guide_map", "off"); } } catch (e) {}
    try { new PerformanceObserver(list => { for (const e of list.getEntries()) window.__uiAuditLCP = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true }); } catch (e) {}
  }, [look, accent, guide || OPT.guide]);
  if (OPT.blockMapbox) await ctx.route(/api\.mapbox\.com|events\.mapbox\.com|tiles\.mapbox\.com/, r => r.abort());
  return ctx;
}
async function clickText(page, selector, text) {
  const loc = page.locator(selector).filter({ hasText: text }).first();
  if (!(await loc.count())) return false;
  try { await loc.click({ timeout: 5000 }); return true; } catch (e) { return false; }
}
async function tryClick(page, selector) {
  const loc = page.locator(selector).first();
  if (!(await loc.count())) return false;
  try { await loc.click({ timeout: 5000 }); return true; } catch (e) { return false; }
}
// the first route the tenant has (from /api/meta, which carries the route list for a signed-in reader)
async function firstRoute(page, store) {
  const rid = await page.evaluate(() => fetch("/api/meta").then(r => r.json()).then(m => (m.routes || [])[0]).then(r => r && r.route_id).catch(() => null));
  drain(store);   // the harness's own read is not the page's
  return rid;
}
async function gotoPage(page, id) {
  await page.evaluate((i) => { location.hash = "#" + i; }, id);
  await page.waitForTimeout(150);
}
async function openFolded(page) {
  // the folded sections only (details.dash-more), not the row menus — those are their own stops
  return page.evaluate(() => { let n = 0; document.querySelectorAll("details.dash-more:not([open])").forEach(d => { d.open = true; n++; }); return n; });
}
async function alertText(page) { return page.locator('[role="alert"]').first().textContent({ timeout: 1000 }).catch(() => ""); }

// the sign-in screens: the public view → Staff sign in → (the code form) → the portal. Returns how it signed in.
async function signIn(page, base, how) {
  await page.goto(base + "/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector('button:has-text("Staff sign in"), [data-guide="rail"], .phone-tabs', { timeout: 60000 });
  if (await page.locator('[data-guide="rail"], .phone-tabs').count()) return "already";
  await page.getByRole("button", { name: "Staff sign in" }).click();
  await page.waitForSelector("#auth-email");
  if (how.email) {
    await page.fill("#auth-email", how.email); await page.fill("#auth-pass", how.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  } else {
    const codes = await page.evaluate(() => fetch("/api/auth/me").then(r => r.json()).then(j => !!j.codes).catch(() => false));
    if (!codes) throw new Error("the server offers no code sign-in (the shared codes are off): pass --email and --password");
    await page.getByRole("button", { name: "Sign in with a team code instead" }).click({ timeout: 15000 });
    await page.waitForSelector("#auth-code");
    await page.fill("#auth-name", how.name || "UI audit");
    await page.fill("#auth-code", how.code);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  }
  try { await page.waitForSelector('[data-guide="rail"], .phone-tabs', { timeout: 30000 }); }
  catch (e) { throw new Error("sign-in did not reach the portal: " + ((await alertText(page)) || (await page.locator(".auth-card p[style]").first().textContent().catch(() => "")) || "no message shown")); }
  return how.email ? "email" : "code";
}

// ---------------------------------------------------------------- the walks ------------------------------------------
async function waitForMap(target) {
  // the map is a top-level `let` in a classic script: visible to evaluate by name, not as window.map. `target` is the
  // map page, or the public view's iframe (embeddedMap)
  const t0 = Date.now();
  while (Date.now() - t0 < 30000) {
    const st = await target.evaluate(() => { try { return (typeof map !== "undefined" && map && map.loaded && map.loaded()) ? "loaded" : (document.querySelector("#p") ? "password" : "loading"); } catch (e) { return "error:" + e.message; } }).catch(() => "nav");
    if (st === "loaded" || st === "password" || st.startsWith("error")) return st;
    await new Promise(r => setTimeout(r, 300));
  }
  return "timeout";
}
// the public view's map is an iframe (/map/?embed=1): its frame, once it has its address; null when none appears in time
async function embeddedMap(page, cap = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < cap) {
    const f = page.frames().find(fr => fr !== page.mainFrame() && /\/map\//.test(fr.url()));
    if (f) return f;
    await page.waitForTimeout(200);
  }
  return null;
}
async function mapStop(page, store, meta) { meta.mapState = await waitForMap(page); return audit(page, store, meta); }
// a first visitor's context (the guide storage not switched off — the existing guide flag of newContext) that carries THIS
// context's cookies: the map access and the staff session the signed-in context has (Playwright hands over the HttpOnly ones
// too). The two guide stops open in one (17 Oct 2026, findings #32 / #33). Returns the page, its store and a close().
async function guideContext(browser, ctx, base, look, accent, w) {
  const g = await newContext(browser, look, accent, w, true);
  await g.addCookies(await ctx.cookies(base));
  const gp = await g.newPage(); const gs = newStore(); watch(gp, gs);
  return { gp, gs, close: () => g.close() };
}
// the hints draw once the tenant is known (the map: its overlay; the app: /api/meta) and are re-placed every second: wait for
// a dot or the strip (8 s at most; the map draws no dot on a phone since decision 8, so its strip is the sign there; a page
// that draws neither is measured as it is, and guide-shown says so)
const waitGuide = (page) => page.waitForSelector(".guide-dot, .guide-strip", { timeout: 8000 }).catch(() => {});
async function evalCall(page, code) { return page.evaluate(code).then(() => true).catch(e => { note(`${code}: ${String(e.message || e).slice(0, 120)}`); return false; }); }

async function walkPortal(browser, base, look, accent, first, widths) {
  const meta = (name, width, extra) => ({ name, width, height: HEIGHT[width] || 800, look, accent, base, ...(extra || {}) });
  const switches = [];
  for (const w of widths) {
    const ctx = await newContext(browser, look, accent, w);
    const page = await ctx.newPage();
    const store = newStore();
    watch(page, store);
    const t0 = Date.now();
    if (first) {
      // 1. the public view and the sign-in screens, at every width, in the first look + accent only (they do not change with the data)
      await page.goto(base + "/", { waitUntil: "domcontentloaded" });
      await page.waitForSelector('button:has-text("Staff sign in")', { timeout: 60000 });
      if (w === DESK_W) REPORT.timings.publicFirstPaintMs = Date.now() - t0;
      await audit(page, store, meta("public", w));
      await page.getByRole("button", { name: "Staff sign in" }).click();
      await page.waitForSelector("#auth-email");
      await audit(page, store, meta("login", w));
      if (w === DESK_W && OPT.deep) {
        await keyboardPass(page, meta("login", w));
        await page.fill("#auth-email", "nobody@example.test"); await page.fill("#auth-pass", "not-the-password");
        await page.getByRole("button", { name: "Sign in", exact: true }).click();
        await page.waitForSelector('[role="alert"]', { timeout: 10000 }).catch(() => {});
        await audit(page, store, meta("login-wrong", w));
        await page.getByRole("button", { name: "Forgot your password?" }).click();
        await audit(page, store, meta("login-forgot", w));
        await page.getByRole("button", { name: "Back to sign in" }).click();
      }
      const codes = await page.evaluate(() => fetch("/api/auth/me").then(r => r.json()).then(j => !!j.codes).catch(() => false));
      if (codes) {
        await page.getByRole("button", { name: "Sign in with a team code instead" }).click({ timeout: 15000 });
        await page.waitForSelector("#auth-code");
        await audit(page, store, meta("login-code", w));
      }
    }
    // 2. sign in (the planner sees every page; Users shows to a code with can_approve)
    const t1 = Date.now();
    await signIn(page, base, OPT.email ? { email: OPT.email, password: OPT.password } : { code: OPT.code });
    if (first && w === DESK_W) { await page.waitForSelector(".dash-cards, [data-empty]", { timeout: 60000 }).catch(() => {}); REPORT.timings.portalFirstDataMs = Date.now() - t1; }
    drain(store);
    // 3. every portal page
    for (const id of PORTAL_PAGES) {
      const ts = Date.now();
      await gotoPage(page, id);
      if (PAGE_TITLE[id]) await page.waitForFunction((t) => { const h = document.querySelector('[data-guide="page-header"] h2'); return h && h.textContent.trim() === t; }, PAGE_TITLE[id], { timeout: 20000 }).catch(() => {});
      const switched = Date.now() - ts;
      await audit(page, store, meta(id, w, { portal: true, page: id }));
      if (first && w === DESK_W) switches.push({ page: id, headerMs: switched });
      // the deep stops: once, at the desk width, in the first look + accent; one that fails is noted, not fatal
      if (OPT.deep && w === DESK_W && first) { try { await deepStops(page, store, meta, id, w); } catch (e) { note(`deep stops on ${id}: ${String(e.message || e).split("\n")[0].slice(0, 160)}`); await leaveFullscreen(page); drain(store); } }
      // the phone's More sheet, once, at the narrowest width (a sheet over the page: not grown, the controls under it not counted)
      if (w === PHONE_W && w < 768 && id === "dashboard" && first) {
        if (await clickText(page, ".phone-tabs button", "More")) { await audit(page, store, meta("phone-more", w, { fixed: true })); await page.keyboard.press("Escape"); await page.waitForTimeout(300); }
        // a first visitor's phone Dashboard with the guide ON (17 Oct 2026, finding #33): a fresh context whose guide storage is
        // not switched off, signed in again (this context's cookies come along, but a code sign-in leaves no hint for the app
        // to resume from, so signIn fills the code; "already" when a login's cookie resumes). As a first visitor sees it: the
        // strip above the tab bar and the dots on the page's features; the tour's own card opens only on "Take the tour" and
        // is not opened. The demo bar's Guide pill is on every portal stop (it needs no guide) — this stop asserts it is on
        // the page (guide-shown) and pictures the hints on a phone, which no other stop does.
        if (OPT.deep) {
          const { gp, gs, close } = await guideContext(browser, ctx, base, look, accent, w);
          try {
            await signIn(gp, base, OPT.email ? { email: OPT.email, password: OPT.password } : { code: OPT.code }); drain(gs);
            await gotoPage(gp, "dashboard");
            await gp.waitForFunction(() => { const h = document.querySelector('[data-guide="page-header"] h2'); return h && h.textContent.trim() === "Dashboard"; }, null, { timeout: 20000 }).catch(() => {});
            await waitGuide(gp);
            await audit(gp, gs, meta("dashboard+guide", w, { portal: true, page: "dashboard", guide: "portal" }));
          } catch (e) { note(`dashboard+guide at ${w}: ${String(e.message || e).split("\n")[0].slice(0, 160)}`); }
          await close();
        }
      }
    }
    // 4. the public map on its own (the staff cookie opens it) and the documents: they take no look, so the first look only
    if (first) {
      await page.goto(base + "/map/", { waitUntil: "domcontentloaded" });
      await mapStop(page, store, meta("map-page", w));
      try {
        if (OPT.deep && w === DESK_W) { await keyboardPass(page, meta("map-page", w)); await mapStates(page, store, meta, w, false); }
        if (OPT.deep && w === PHONE_W && w < 768) {
          await mapStates(page, store, meta, w, true);
          // a first visitor's phone: the map's tour strip on (its own stop, so the hints are measured once and named). The
          // context carries this context's cookies — the map access — and the guide storage is not switched off: until
          // 17 Oct 2026 it had no cookie, so this stop was the map's PASSWORD page in every run (finding #32) and the dots were
          // never measured; it asserts the strip, NO dot on the phone (decision 8, 18 Oct 2026) and that the map loaded.
          const { gp, gs, close } = await guideContext(browser, ctx, base, look, accent, w);
          await gp.goto(base + "/map/", { waitUntil: "domcontentloaded" });
          const st = await waitForMap(gp); await waitGuide(gp);
          await audit(gp, gs, { ...meta("map-page+guide", w, { fixed: true, guide: "map" }), mapState: st });
          await close();
        }
      } catch (e) { note(`map states at ${w}: ${String(e.message || e).split("\n")[0].slice(0, 160)}`); drain(store); }
      const month = await page.evaluate(async () => { const m = await (await fetch("/api/meta")).json(); const d = new Date(); const sy = m && m.months && m.months.start_year;
        return sy ? (d.getFullYear() - sy) * 12 + d.getMonth() + 1 : 10; }).catch(() => 10);
      REPORT.month = month;
      const docs = [["help", "/help/"], ["help-technical", "/help/technical/"], ["bulletin", "/bulletin/?month=" + month], ["bulletin-leaflet", "/bulletin/leaflet/?month=" + month],
                    ["landing", "/landing/"], ["privacy", "/landing/privacy.html"], ["thanks", "/landing/thanks.html"], ["landing-error", "/landing/error.html"]];
      await ctx.route(/^https:\/\/(app\.)?wayscope\.co\.uk\//, r => r.abort());   // the landing page's links never leave this machine
      for (const [name, url] of docs) {
        await page.goto(base + url, { waitUntil: "domcontentloaded" });
        await audit(page, store, meta(name, w));
        if (OPT.deep && w === DESK_W) await keyboardPass(page, meta(name, w));
      }
      await ctx.unroute(/^https:\/\/(app\.)?wayscope\.co\.uk\//);
    }
    // 5. error states, once at the desk width
    if (first && OPT.deep && w === DESK_W) { try { await errorStates(page, ctx, store, meta, w); } catch (e) { note(`error states: ${String(e.message || e).split("\n")[0].slice(0, 160)}`); await ctx.setOffline(false).catch(() => {}); } }
    await ctx.close();
  }
  if (first) REPORT.timings.pageSwitches = switches;
}

// the screens behind a click, at the desk width in the first look
async function deepStops(page, store, meta, id, w) {
  await keyboardPass(page, meta(id, w));
  if (id === "dashboard") {
    for (const [name, text] of [["dashboard+filters", "More filters"], ["dashboard+bulletin-menu", "Monthly bulletin"]]) {
      if (await clickText(page, "details.row-menu > summary", text)) { await audit(page, store, meta(name, w)); await page.keyboard.press("Escape"); await page.evaluate(() => document.querySelectorAll("details.row-menu[open]").forEach(d => { d.open = false; })); }
    }
    if (await openFolded(page)) {
      await audit(page, store, meta("dashboard+open", w));
      if (await tryClick(page, ".rd-chev:visible")) await audit(page, store, meta("dashboard+row", w));
    }
    if (await clickText(page, '[data-guide="dash-wall"]', "Big screen")) {
      await audit(page, store, meta("dashboard-bigscreen", w));
      for (const [name, text] of [["bigscreen-rotate", "Rotate"], ["bigscreen-one", "One section"]]) if (await clickText(page, ".dash-wallbar button", text)) await audit(page, store, meta(name, w));
      await page.keyboard.press("Escape"); await page.waitForTimeout(300); await leaveFullscreen(page);
      if (await page.locator('[data-guide="dash-wall"]').filter({ hasText: "Exit big screen" }).count()) await clickText(page, '[data-guide="dash-wall"]', "Exit big screen");
    }
  }
  if (id === "forecasts") {
    if (await tryClick(page, ".rd-chev:visible")) await audit(page, store, meta("forecasts+row", w));
    if (await clickText(page, ".unit-sw-seg button", "Lorries")) { await audit(page, store, meta("forecasts+lorries", w)); await clickText(page, ".unit-sw-seg button", "Loads"); }
  }
  if (id === "carbon" && await openFolded(page)) await audit(page, store, meta("carbon+open", w));
  if (id === "locations" && await tryClick(page, "main table tbody tr:visible")) { await page.waitForTimeout(500); await audit(page, store, meta("locations+edit", w)); }
  if (id === "lookahead") {
    for (const [k, t] of [["account", "Account"], ["horizon", "Horizon"]]) if (await clickText(page, '[data-guide="lookahead-tabs"] button', t)) await audit(page, store, meta("lookahead-" + k, w));
    await clickText(page, '[data-guide="lookahead-tabs"] button', "Commit");
  }
  if (id === "config") {
    for (const t of CONFIG_TABS.slice(1)) if (await clickText(page, ".cfg-nav-item", t)) await audit(page, store, meta("config-" + t.toLowerCase().replace(/[^a-z]+/g, "-").replace(/-$/, ""), w));
    await clickText(page, ".cfg-nav-item", CONFIG_TABS[0]);
    // Save, on the copy: the page's saved state (its status line) is a screen too. Needs the admin token (a code is not an admin).
    await page.locator('[data-guide="page-header"] details.row-menu > summary').first().click().catch(() => {});
    await page.locator('[data-guide="page-header"] input[aria-label="Admin token"]').fill("ui-audit-admin-token").catch(() => {});
    await page.keyboard.press("Escape");
    if (await clickText(page, '[data-guide="page-header"] button', "Save")) { await page.waitForTimeout(800); await audit(page, store, meta("config+saved", w)); }
  }
  if (id === "users") {
    // a code is not an admin: the list wants the token. The locked screen first (its own stop), then the table.
    const tok = page.locator('input[aria-label="Admin token"]').first();
    if (await tok.count()) {
      await tok.fill("ui-audit-admin-token"); await tok.press("Enter");
      await page.waitForSelector("table, [data-empty]", { timeout: 15000 }).catch(() => {});
      await audit(page, store, meta("users+table", w));
    }
  }
}

// the public map's states: presets, the collision layer, a route's drawer, share, export, conditions, Play; on a phone the sheet, Layers, a route card
async function mapStates(page, store, meta, w, phone) {
  if (phone) {
    if (await evalCall(page, "toggleSheet()")) { await page.waitForTimeout(500); await mapStop(page, store, meta("map-page+sheet", w)); }
    const btn = (await page.locator("#m-layers-btn").isVisible().catch(() => false)) ? "#m-layers-btn" : (await page.locator("#menu-toggle").isVisible().catch(() => false)) ? "#menu-toggle" : null;
    if (btn) { await page.locator(btn).click(); await page.waitForTimeout(500); await mapStop(page, store, meta("map-page+layers", w)); await page.keyboard.press("Escape"); await page.waitForTimeout(300); }
    const rid = await firstRoute(page, store);
    if (rid && await evalCall(page, `openRouteCard(${JSON.stringify(rid)})`)) { await page.waitForTimeout(600); await mapStop(page, store, meta("map-page+route-card", w)); }
    return;
  }
  const presets = await page.evaluate(() => [...document.querySelectorAll(".preset-chip")].map(b => b.dataset.preset)).catch(() => []);
  for (const p of presets) if (await evalCall(page, `applyPreset(${JSON.stringify(p)})`)) { await page.waitForTimeout(800); await mapStop(page, store, meta("map-page+preset-" + p.replace(/[^a-z0-9]+/gi, "-"), w)); }
  // the layers a planner ticks: collisions, the council areas, the community considerations (each hidden until ticked)
  for (const [name, id] of [["collisions", "#layer-collisions"], ["council", "#layer-areas-district"], ["community", "#layer-community"]]) {
    const box = page.locator(id);
    if (await box.count()) { await box.check({ force: true }).catch(() => {}); await page.waitForTimeout(900); await mapStop(page, store, meta("map-page+" + name, w)); await box.uncheck({ force: true }).catch(() => {}); }
  }
  const rid = await firstRoute(page, store);
  if (rid && await evalCall(page, `selectRoute(${JSON.stringify(rid)})`)) { await page.waitForTimeout(800); await mapStop(page, store, meta("map-page+route-drawer", w)); }
  for (const [name, fn] of [["share", "openSharePanel()"], ["export", "openRouteExport()"], ["conditions", "toggleConditions()"]]) {
    if (await evalCall(page, fn)) { await page.waitForTimeout(500); await mapStop(page, store, meta("map-page+" + name, w)); await page.keyboard.press("Escape"); await page.waitForTimeout(200); }
  }
  if (await page.locator("#tl-play").count()) { await page.locator("#tl-play").click().catch(() => {}); await page.waitForTimeout(2500); await mapStop(page, store, meta("map-page+playing", w)); await page.locator("#tl-play").click().catch(() => {}); }
}

// a read that fails, a search with no match, the app offline. The walk before this ends on the landing page's error
// page, and gotoPage only sets the hash: so the app comes back first (the session cookie signs it back in; the code
// again if not), and each error stop asserts that it is the app's page — the title the portal carries, the header the
// page named — and that the page shows the failure it is named for. Until 17 Oct "forecasts-error" and
// "offline-lookahead" were pictures of /landing/error.html.
async function errorStates(page, ctx, store, meta, w) {
  const base = meta("", w).base;
  await signIn(page, base, OPT.email ? { email: OPT.email, password: OPT.password } : { code: OPT.code });
  const appTitle = await page.title();
  drain(store);
  // what the page shows for the failure: the app's EmptyState (data-empty="error", an alert) or its inline notice
  const shown = () => page.evaluate(() => {
    const re = /did not load|Couldn't load|did not answer|Try again/;
    const el = document.querySelector('[data-empty="error"], [role="alert"]')
      || [...document.querySelectorAll("main *")].find(e => re.test(e.textContent) && ![...e.children].some(c => re.test(c.textContent)));
    if (!el) return "";
    const how = el.getAttribute("data-empty") ? "data-empty=" + el.getAttribute("data-empty") : el.getAttribute("role") ? "role=" + el.getAttribute("role") : "notice";
    return how + ": " + el.textContent.trim().replace(/\s+/g, " ").slice(0, 90);
  }).catch(() => "");
  const isApp = (stop, want, state) => {
    stop.errorShown = state || undefined;
    ok(`${stop.name}: the stop is the app's ${want} page, not a document (title "${stop.title}", header "${stop.pageTitle}")`, stop.title === appTitle && stop.pageTitle === want);
    ok(`${stop.name}: the page shows the failure it is named for`, !!state, "no error state or notice found on the page");
  };
  await ctx.route(/\/api\/forecasts(\?|$)/, r => r.abort());
  await gotoPage(page, "dashboard"); await page.waitForTimeout(300);
  await gotoPage(page, "forecasts");
  await page.waitForSelector('[data-empty="error"], [role="alert"]', { timeout: 15000 }).catch(() => {});
  isApp(await audit(page, store, meta("forecasts-error", w, { portal: true, page: "forecasts", cut: /\/api\/forecasts(\?|$)/ })), "Forecasts", await shown());
  await ctx.unroute(/\/api\/forecasts(\?|$)/);
  await gotoPage(page, "dashboard"); await page.waitForTimeout(300); await gotoPage(page, "forecasts");
  await settle(page, store);
  const search = page.locator('input[aria-label="Search forecast lines"]');
  if (await search.count()) { await search.fill("zzzz-no-such-line"); await page.waitForTimeout(500); await audit(page, store, meta("forecasts-nomatch", w)); await search.fill(""); }
  await ctx.setOffline(true);
  await gotoPage(page, "lookahead"); await page.waitForTimeout(1500);
  isApp(await audit(page, store, meta("offline-lookahead", w, { portal: true, page: "lookahead", cut: /./ })), "Look-ahead", await shown());
  await ctx.setOffline(false);
}

// the team (submitter) role: fewer pages, no approve, a locked team
async function walkTeam(browser, base) {
  const look = LOOKS[0], w = DESK_W;
  const ctx = await newContext(browser, look, "orange", w);
  const page = await ctx.newPage(); const store = newStore(); watch(page, store);
  const meta = (name, extra) => ({ name, width: w, height: HEIGHT[w], look, accent: "orange", base, ...(extra || {}) });
  try { await signIn(page, base, { code: OPT.teamCode, name: "UI audit team" }); }
  catch (e) { note("team walk skipped: " + e.message); await ctx.close(); return; }
  drain(store);
  for (const id of TEAM_PAGES) {
    await gotoPage(page, id);
    if (PAGE_TITLE[id]) await page.waitForFunction((t) => { const h = document.querySelector('[data-guide="page-header"] h2'); return h && h.textContent.trim() === t; }, PAGE_TITLE[id], { timeout: 20000 }).catch(() => {});
    await audit(page, store, meta("team-" + id, { portal: true, page: id }));
    if (OPT.deep && (id === "submit" || id === "forecasts")) await keyboardPass(page, meta("team-" + id));
  }
  await ctx.close();
}

// the login user (what every person is after the codes go, D49): an invite link → set a password → the portal as an
// admin (the Users table without a token) → a reload while signed in → a dead link
async function walkLogin(browser, base) {
  const look = LOOKS[0];
  const made = await (async () => {
    const r = await fetch(base + "/api/admin/users?token=ui-audit-admin-token", { method: "POST", headers: { "Content-Type": "application/json", "X-Wayscope": "1" },
      body: JSON.stringify({ name: "UI audit admin", email: "ui-audit@example.test", role: "admin" }) }).catch(e => ({ ok: false, statusText: String(e) }));
    if (!r.ok) { note("login walk skipped: POST /api/admin/users answered " + r.status + " " + (r.statusText || "")); return null; }
    const j = await r.json();
    if (!j.link) { note("login walk skipped: the invite answered without a link (a sender is set?)"); return null; }
    return j.link;
  })();
  if (!made) return;
  const link = made.replace(/^https?:\/\/[^/]+/, base);
  for (const w of [DESK_W, PHONE_W].filter((x, i, a) => a.indexOf(x) === i)) {
    const ctx = await newContext(browser, look, "orange", w);
    const page = await ctx.newPage(); const store = newStore(); watch(page, store);
    const meta = (name, extra) => ({ name, width: w, height: HEIGHT[w], look, accent: "orange", base, ...(extra || {}) });
    if (w !== DESK_W) {
      // the phone, as the login user (the header's account menu, not Sign out): the password was set at the desk width first
      try {
        await signIn(page, base, { email: "ui-audit@example.test", password: "ui-audit-password-1" });
        drain(store);
        for (const id of ["dashboard", "lookahead"]) { await gotoPage(page, id); await audit(page, store, meta("login-user-" + id, { portal: true, page: id })); }
      } catch (e) { note("login walk on the phone: " + String(e.message || e).split("\n")[0].slice(0, 160)); }
      await ctx.close(); continue;
    }
    await page.goto(link, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#set-pw, .auth-card", { timeout: 30000 }).catch(() => {});
    await audit(page, store, meta("setpw", w));
    if (OPT.deep) await keyboardPass(page, meta("setpw"));
    await page.fill("#set-pw", "ui-audit-password-1"); await page.fill("#set-pw2", "ui-audit-password-1");
    await page.getByRole("button", { name: "Save and sign in" }).click();
    try { await page.waitForSelector('[data-guide="rail"]', { timeout: 30000 }); } catch (e) { note("login walk: the invite did not sign in — " + (await alertText(page))); await ctx.close(); return; }
    drain(store);
    for (const id of ["dashboard", "users", "forecasts"]) {
      await gotoPage(page, id);
      if (PAGE_TITLE[id]) await page.waitForFunction((t) => { const h = document.querySelector('[data-guide="page-header"] h2'); return h && h.textContent.trim() === t; }, PAGE_TITLE[id], { timeout: 20000 }).catch(() => {});
      if (id === "users") await page.waitForSelector("table, [data-empty]", { timeout: 15000 }).catch(() => {});
      await audit(page, store, meta("login-user-" + id, { portal: true, page: id }));
      if (OPT.deep && id === "users") await keyboardPass(page, meta("login-user-users"));
    }
    // a reload while signed in: "Signing you back in…" then the portal
    await page.reload({ waitUntil: "domcontentloaded" });
    const resumed = await page.locator('[role="status"]:has-text("Signing you back in")').count();
    await page.waitForSelector('[data-guide="rail"]', { timeout: 30000 }).catch(() => {});
    await audit(page, store, meta("login-user-resumed", { portal: true, page: "forecasts" }));   // the page it was on (the hash wins)
    ok("a reload keeps a login signed in (the session cookie)", !!(await page.locator('[data-guide="rail"]').count()), resumed ? "" : "no resume notice seen");
    // sign out: the public view, whose map is an iframe — let the map finish (loaded, or its password page) and set
    // its events aside, so nothing of it counts against the next stop (what it did is on the record as a note). Then
    // a dead invite link, from a BLANK page: the app reads an email link once, as the page loads, and a goto that
    // changes only the hash is no load — until 17 Oct the "linkerr" stop was this public view, its map blank, the
    // frame's "… is not defined" errors counted against it; the dead-link note was never pictured.
    await page.getByRole("button", { name: "Sign out" }).click().catch(() => {});
    const frame = await embeddedMap(page);
    const mapAfter = frame ? await waitForMap(frame) : "no iframe";
    await settle(page, store);
    const left = drain(store);
    if ((mapAfter !== "loaded" && mapAfter !== "password") || left.errors.length) note(`after Sign out, the public view's map: ${mapAfter}${left.errors.length ? `, ${left.errors.length} error(s), first: ${left.errors[0]}` : ""}`);
    await page.goto("about:blank");
    await page.goto(base + "/#invite=" + "x".repeat(40), { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".auth-card", { timeout: 30000 }).catch(() => {});
    const card = await page.locator(".auth-card h1").first().textContent({ timeout: 1000 }).catch(() => "");
    const dead = await audit(page, store, meta("linkerr", { expectGone: /\/api\/auth\/check$/ }));
    dead.cardTitle = card || undefined;
    ok(`linkerr: a dead invite link shows the app's note, not the public view (card "${card}", title "${dead.title}")`,
       /no longer works/.test(card) && !(await page.locator("iframe").count()));
    await ctx.close();
  }
}

// a tenant with no data: the boots-empty app
async function walkEmpty(browser) {
  let server;
  try { server = await startServer({ empty: true }); } catch (e) { note("empty-tenant walk skipped: " + e.message); return; }
  try {
    const look = LOOKS[0], w = DESK_W;
    const ctx = await newContext(browser, look, "orange", w);
    const page = await ctx.newPage(); const store = newStore(); watch(page, store);
    const meta = (name, extra) => ({ name, width: w, height: HEIGHT[w], look, accent: "orange", base: server.base, ...(extra || {}) });
    await signIn(page, server.base, { code: OPT.code });
    drain(store);
    for (const id of ["dashboard", "lookahead", "routes", "submit"]) {
      await gotoPage(page, id);
      if (PAGE_TITLE[id]) await page.waitForFunction((t) => { const h = document.querySelector('[data-guide="page-header"] h2'); return h && h.textContent.trim() === t; }, PAGE_TITLE[id], { timeout: 20000 }).catch(() => {});
      await audit(page, store, meta("empty-" + id, { portal: true, page: id }));
    }
    await ctx.close();
  } catch (e) { note("empty-tenant walk stopped: " + e.message); }
  finally { await server.stop(); }
}

async function walkUnsigned(browser, base) {
  // a visitor without any cookie: the map's password page
  const look = LOOKS[0];
  const meta = (name, w) => ({ name, width: w, height: HEIGHT[w] || 800, look, accent: "orange", base });
  for (const w of WIDTHS) {
    const ctx = await newContext(browser, look, "orange", w);
    const page = await ctx.newPage(); const store = newStore(); watch(page, store);
    await page.goto(base + "/map/", { waitUntil: "domcontentloaded" });
    await audit(page, store, meta("map-password", w));
    if (w === DESK_W) {
      if (OPT.deep) await keyboardPass(page, meta("map-password", w));
      // the wrong password, then the right one — the map opens with the map cookie alone
      await page.fill("#p", "not-the-password"); await page.click('#f button[type="submit"]'); await page.waitForTimeout(600);
      await audit(page, store, meta("map-password-wrong", w));
      await page.fill("#p", OPT.mapPassword); await page.click('#f button[type="submit"]');
      await page.waitForTimeout(1500);
      const st = await waitForMap(page);
      ok("the map password opens the public map (the map cookie alone)", st === "loaded", st);
      await audit(page, store, { ...meta("map-public", w), mapState: st });
      if (OPT.deep) await keyboardPass(page, meta("map-public", w));
    }
    await ctx.close();
  }
}

// ---------------------------------------------------------------- compare with an earlier run -------------------------
// the harness's own server origin (http://127.0.0.1:<port>) is stripped from a URL or a message in a key: the port is picked per
// run (8834, 8836, …), so until 17 Oct 2026 a run on another port showed each no-http-errors / requests-failed row as one new +
// one gone (finding #34). Both runs' keys are made here from their reports, so the change itself shows nothing in a compare.
const noOrigin = (s) => String(s).replace(/^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/, "");
function findingKeys(stop) {
  const keys = [];
  const one = (id, x) => `${stop.name}|${stop.width}|${stop.look}|${stop.accent}|${id}|${x && typeof x === "object" && (x.id || x.sel || x.url || x.tag) ? (x.id || x.sel || (x.url ? noOrigin(x.url) : null) || x.tag) + (x.text ? " " + x.text : "") : typeof x === "string" ? noOrigin(x).slice(0, 80) : ""}`;
  for (const c of (stop.checks || [])) if (!c.ok) {
    if (Array.isArray(c.detail)) for (const x of c.detail) keys.push(one(c.id, x)); else keys.push(one(c.id, null));
  }
  for (const w of (stop.warnings || [])) {
    if (Array.isArray(w.detail)) for (const x of w.detail) keys.push(one(w.id, x)); else keys.push(one(w.id, null));
  }
  return keys;
}
// a run before 17 Oct was the bundled Chromium; one from before the Dark / Blue pass (decision 15) has no extraPasses and does
// not pair with one that has it. --strict-44 is a grading, not a shape, of the same stops: a strict run pairs with a plain one.
function sameShape(a, b) { const k = (o) => [o.widths, o.looks, o.extraAccents, o.extraPasses || [], o.pages, o.browser || "chromium"]; return JSON.stringify(k(a)) === JSON.stringify(k(b)); }
async function compareRuns(browser, prevPath) {
  if (prevPath === "latest") {
    const runs = fs.readdirSync(OPT.out).filter(d => d !== STAMP && fs.existsSync(path.join(OPT.out, d, "report.json"))).sort().reverse();
    let pick = null;
    for (const d of runs) {
      try { const r = JSON.parse(fs.readFileSync(path.join(OPT.out, d, "report.json"), "utf8"));
        if (!sameShape(r.options || {}, REPORT.options)) { note(`compare: ${d} skipped, a different shape`); continue; }
        if ((r.failures || []).some(f => /the run stopped/.test(f))) { note(`compare: ${d} skipped, it stopped early`); continue; }
        pick = d; break; } catch (e) {}
    }
    if (!pick) { note("compare: no earlier run of this shape in " + OPT.out); return null; }
    prevPath = path.join(OPT.out, pick, "report.json");
  }
  const prev = JSON.parse(fs.readFileSync(prevPath, "utf8"));
  const prevDir = path.dirname(prevPath);
  const now = new Set(REPORT.stops.flatMap(findingKeys)), was = new Set(prev.stops.flatMap(findingKeys));
  const diff = { against: prevPath, prevStamp: prev.stamp, prevHead: prev.head, newFindings: [...now].filter(k => !was.has(k)), goneFindings: [...was].filter(k => !now.has(k)), shots: [] };
  // pixels, compared in the browser (Chromium decodes the PNGs; no image package needed); the masks of both runs are skipped
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.setContent("<html><body></body></html>");
  const diffDir = path.join(RUN_DIR, "diff");
  for (const s of REPORT.stops) {
    if (!s.shot) continue;
    const p = prev.stops.find(x => x.shot === s.shot);
    if (!p) { diff.shots.push({ shot: s.shot, status: "new" }); continue; }
    const a = path.join(RUN_DIR, s.shot), b = path.join(prevDir, p.shot);
    if (!fs.existsSync(b)) { diff.shots.push({ shot: s.shot, status: "no-previous-file" }); continue; }
    const r = await page.evaluate(async ([A, B, masks]) => {
      const load = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
      const [ia, ib] = await Promise.all([load(A), load(B)]);
      const w = Math.max(ia.width, ib.width), h = Math.max(ia.height, ib.height);
      const cv = (img) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0); return g.getImageData(0, 0, w, h).data; };
      const da = cv(ia), db = cv(ib);
      const masked = new Uint8Array(w * h);
      for (const [x, y, mw, mh] of masks) for (let yy = Math.max(0, y); yy < Math.min(h, y + mh); yy++) for (let xx = Math.max(0, x); xx < Math.min(w, x + mw); xx++) masked[yy * w + xx] = 1;
      const out = document.createElement("canvas"); out.width = w; out.height = h; const g = out.getContext("2d"); const od = g.createImageData(w, h);
      let n = 0, counted = 0;
      for (let i = 0, p = 0; i < da.length; i += 4, p++) {
        const m = masked[p];
        const d = Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]);
        const changed = !m && d > 48; if (changed) n++; if (!m) counted++;
        od.data[i] = changed ? 220 : Math.round(da[i] * 0.25 + 190); od.data[i + 1] = changed ? 30 : Math.round(da[i + 1] * 0.25 + 190); od.data[i + 2] = m ? 120 : changed ? 30 : Math.round(da[i + 2] * 0.25 + 190); od.data[i + 3] = 255;
      }
      g.putImageData(od, 0, 0);
      const pct = counted ? Math.round(n * 10000 / counted) / 100 : 0;
      return { pct, sizeChanged: ia.width !== ib.width || ia.height !== ib.height, png: pct > 0.5 ? out.toDataURL("image/png") : null };
    }, ["data:image/png;base64," + fs.readFileSync(a).toString("base64"), "data:image/png;base64," + fs.readFileSync(b).toString("base64"), [...(s.masks || []), ...(p.masks || [])]]);
    const row = { shot: s.shot, pct: r.pct, sizeChanged: r.sizeChanged, status: r.pct > 0.5 || r.sizeChanged ? "changed" : "same" };
    if (r.png) { fs.mkdirSync(diffDir, { recursive: true }); const f = path.join(diffDir, path.basename(s.shot)); fs.writeFileSync(f, Buffer.from(r.png.split(",")[1], "base64")); row.diff = "diff/" + path.basename(s.shot); }
    diff.shots.push(row);
  }
  await ctx.close();
  REPORT.compare = diff;
  const changed = diff.shots.filter(x => x.status === "changed");
  console.log(`\ncompare with ${prev.stamp} (${prev.head}): ${diff.newFindings.length} new finding(s), ${diff.goneFindings.length} gone, ${changed.length} of ${diff.shots.length} screenshot(s) changed > 0.5 %`);
  for (const k of diff.newFindings.slice(0, 20)) console.log("  new  " + k);
  for (const k of diff.goneFindings.slice(0, 20)) console.log("  gone " + k);
  for (const c of changed.slice(0, 30)) console.log(`  changed ${c.pct} %  ${c.shot}`);
  return diff;
}

// ---------------------------------------------------------------- the written report ---------------------------------
function summaryTables() {
  const byCheck = {};
  for (const s of REPORT.stops) for (const c of s.checks) { const k = byCheck[c.id] = byCheck[c.id] || { pass: 0, fail: 0, widths: {} }; if (c.ok) k.pass++; else { k.fail++; k.widths[s.width] = (k.widths[s.width] || 0) + 1; } }
  const warnBy = {};
  for (const s of REPORT.stops) for (const w of s.warnings || []) { const n = Array.isArray(w.detail) ? w.detail.length : 1; warnBy[w.id] = (warnBy[w.id] || 0) + n; }
  const axeBy = {};
  const addAxe = (v, s) => { const k = axeBy[v.id] = axeBy[v.id] || { impact: v.impact, help: v.help, stops: 0, nodes: 0, where: new Set() }; k.stops++; k.nodes += v.count; k.where.add(s.name); };
  for (const s of REPORT.stops) { for (const c of s.checks) if (c.id === "axe-wcag" && !c.ok) for (const v of c.detail) addAxe(v, s);
    for (const w of s.warnings || []) if (w.id === "axe-minor") for (const v of w.detail) addAxe(v, s); }
  // colour pairs: one token value fixes every node that shares it — the list a fix is planned from
  const pairs = {};
  for (const s of REPORT.stops) for (const c of s.checks) if (c.id === "axe-wcag" && !c.ok) for (const v of c.detail) if (v.id === "color-contrast") for (const n of v.nodes) {
    const m = /contrast of ([\d.]+) \(foreground color: (#[0-9a-f]+), background color: (#[0-9a-f]+), font size: ([\d.]+)pt \(([\d.]+)px\), font weight: (\w+)\)/i.exec(n.why);
    if (!m) continue;
    const k = `${m[2]} on ${m[3]} · ${m[5]} px ${m[6]}`;
    const p = pairs[k] = pairs[k] || { ratio: +m[1], fg: m[2], bg: m[3], px: +m[5], weight: m[6], nodes: 0, looks: new Set(), screens: new Set(), sample: n.html.slice(0, 90) };
    p.nodes++; p.looks.add(s.look); p.screens.add(s.name);
  }
  const colourPairs = Object.values(pairs).map(p => ({ ...p, looks: [...p.looks], screens: [...p.screens] })).sort((a, b) => a.ratio - b.ratio || b.nodes - a.nodes);
  // what --strict-44 would fail in a plain run: the 44 px rows that are not set apart (a strict run counts them in byCheck instead)
  let strict44Would = 0;
  if (!OPT.strict44) for (const s of REPORT.stops) for (const w of s.warnings || []) if (w.id === "targets-44px") strict44Would += w.detail.filter(r => !r.spaced).length;
  return { byCheck, warnBy, axeBy: Object.fromEntries(Object.entries(axeBy).map(([k, v]) => [k, { ...v, where: [...v.where] }])), colourPairs, strict44Would };
}
function writeSummaryMd(t) {
  const lines = [`# UI audit ${REPORT.stamp} — ${REPORT.head || "?"}`, "",
    `${REPORT.stops.length} stops · widths ${WIDTHS.join(", ")} · looks ${LOOKS.join(", ")}${EXTRA_ACCENTS.length ? " · accents " + EXTRA_ACCENTS.join(", ") + " at " + DESK_W : ""}${EXTRA_PASSES.map(p => " · + " + p.look + " / " + p.accent + " at " + p.widths.join(", ")).join("")}${OPT.strict44 ? " · strict 44 px" : ""} · ${REPORT.browser ? REPORT.browser.ran + " " + REPORT.browser.version : ""} · ${REPORT.secs} s`,
    `**${PASS} passed, ${FAIL.length} failed.** First paint of the public view ${REPORT.timings.publicFirstPaintMs} ms; the portal's first data after sign-in ${REPORT.timings.portalFirstDataMs} ms.`, "",
    "## Checks (one per stop)", "", "| Check | Pass | Fail | Failing widths |", "|---|---:|---:|---|"];
  for (const [k, v] of Object.entries(t.byCheck)) lines.push(`| ${k} | ${v.pass} | ${v.fail} | ${Object.entries(v.widths).map(([w, n]) => w + " (" + n + ")").join(", ")} |`);
  lines.push("", "## Warnings (not counted as failures)", "", "| Warning | Items across all stops |", "|---|---:|");
  for (const [k, v] of Object.entries(t.warnBy)) lines.push(`| ${k} | ${v} |`);
  if (t.strict44Would) lines.push("", `targets-44px: ${t.strict44Would} of the rows above are neither inline nor set apart and FAIL without --no-strict-44 (decision 14; the default since the phone branch, 18 Oct 2026).`);
  lines.push("", "## axe rules hit", "", "| Rule | Impact | Stops | Nodes | Screens |", "|---|---|---:|---:|---|");
  for (const [k, v] of Object.entries(t.axeBy).sort((a, b) => b[1].stops - a[1].stops)) lines.push(`| ${k} | ${v.impact} | ${v.stops} | ${v.nodes} | ${v.where.slice(0, 8).join(", ")}${v.where.length > 8 ? " …" : ""} |`);
  if (t.colourPairs.length) { lines.push("", "## Colour pairs failing contrast (one token value fixes every node that shares it), worst first", "", "| Ratio | Foreground on background | Size | Nodes | Looks | Screens | Sample |", "|---:|---|---|---:|---|---|---|");
    for (const p of t.colourPairs.slice(0, 40)) lines.push(`| ${p.ratio} | ${p.fg} on ${p.bg} | ${p.px} px ${p.weight} | ${p.nodes} | ${p.looks.join(", ")} | ${p.screens.slice(0, 5).join(", ")}${p.screens.length > 5 ? " …" : ""} | \`${p.sample.replace(/\|/g, "¦")}\` |`); }
  if (REPORT.timings.pageSwitches) { lines.push("", `## Page switches at ${DESK_W} px (first look): hash set → the page header shows the new title`, "", "| Page | ms |", "|---|---:|"); for (const p of REPORT.timings.pageSwitches) lines.push(`| ${p.page} | ${p.headerMs} |`); }
  if (REPORT.notes.length) { lines.push("", "## Notes", ""); for (const n of REPORT.notes) lines.push("- " + n); }
  if (FAIL.length) { lines.push("", "## Failures", ""); for (const f of FAIL) lines.push("- " + f); }
  if (REPORT.compare) { const c = REPORT.compare; lines.push("", `## Compared with ${c.prevStamp} (${c.prevHead})`, "", `${c.newFindings.length} new, ${c.goneFindings.length} gone, ${c.shots.filter(s => s.status === "changed").length} screenshots changed`);
    for (const k of c.newFindings) lines.push("- new: " + k); for (const k of c.goneFindings) lines.push("- gone: " + k); for (const s of c.shots.filter(s => s.status === "changed")) lines.push(`- changed ${s.pct} %: ${s.shot}`); }
  fs.writeFileSync(path.join(RUN_DIR, "summary.md"), lines.join("\n") + "\n");
}
function writeHtml() {
  // the report's own data, embedded; every "<" from a page sample is escaped so no sample can end the script or open a comment
  const json = JSON.stringify(REPORT).replace(/</g, "\\u003c");
  const html = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UI audit ${REPORT.stamp}</title>
<style>
:root{--ink:#1e293b;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--card:#fff;--red:#dc2626;--gold:#d97706;--green:#059669}
@media(prefers-color-scheme:dark){:root{--ink:#e5e7eb;--muted:#9ca3af;--line:#334155;--bg:#0f172a;--card:#1e293b}}
body{margin:0;font:14px/1.45 Inter,system-ui,sans-serif;color:var(--ink);background:var(--bg)}
header{padding:16px 20px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:2;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
h1{font-size:18px;margin:0}select,input{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px;padding:16px 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.card img{display:block;width:100%;max-height:420px;object-fit:cover;object-position:top;border-bottom:1px solid var(--line);background:#fff}
.card .b{padding:10px 12px}.card h3{margin:0 0 4px;font-size:14px}.m{color:var(--muted);font-size:12px}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;margin:2px 4px 2px 0;border:1px solid var(--line)}
.fail{background:rgba(220,38,38,.12);color:var(--red);border-color:var(--red)}.warn{background:rgba(217,119,6,.12);color:var(--gold);border-color:var(--gold)}.ok{color:var(--green)}
details{margin-top:6px}summary{cursor:pointer;color:var(--muted);font-size:12px}pre{white-space:pre-wrap;font-size:11px;max-height:260px;overflow:auto;background:var(--bg);padding:8px;border-radius:6px}
table{border-collapse:collapse;margin:0 20px 16px}td,th{border:1px solid var(--line);padding:4px 8px;text-align:left;font-size:13px}th{background:var(--card)}
.sum{padding:12px 20px 0;display:flex;gap:30px;flex-wrap:wrap}
</style>
<header><h1>UI audit ${REPORT.stamp} · ${REPORT.head || ""}</h1>
<label>Screen <select id="fPage"><option value="">all</option></select></label>
<label>Width <select id="fW"><option value="">all</option></select></label>
<label>Look <select id="fLook"><option value="">all</option></select></label>
<label>Accent <select id="fAcc"><option value="">all</option></select></label>
<label>Check <select id="fCheck"><option value="">any</option></select></label>
<label><input type="checkbox" id="fBad"> only stops with failures</label>
<label><input type="checkbox" id="fWarn"> or warnings</label>
<span id="count" class="m"></span></header>
<div class="sum" id="sum"></div>
<div id="tables"></div>
<div class="grid" id="grid"></div>
<script>
const R = ${json};
const $ = (s) => document.querySelector(s);
const uniq = (k) => [...new Set(R.stops.map(s => s[k]))].filter(x => x != null).sort((a, b) => (typeof a === "number" ? a - b : String(a).localeCompare(String(b))));
for (const [id, k] of [["#fPage", "name"], ["#fW", "width"], ["#fLook", "look"], ["#fAcc", "accent"]]) for (const v of uniq(k)) $(id).insertAdjacentHTML("beforeend", "<option>" + v + "</option>");
for (const v of [...new Set(R.stops.flatMap(s => [...s.checks.map(c => c.id), ...(s.warnings || []).map(w => w.id)]))].sort()) $("#fCheck").insertAdjacentHTML("beforeend", "<option>" + v + "</option>");
$("#sum").innerHTML = "<div><b>" + R.totals.passed + "</b> passed · <b class='" + (R.totals.failed ? "fail" : "ok") + "'>" + R.totals.failed + "</b> failed</div>"
  + "<div>" + R.stops.length + " stops · " + R.secs + " s</div><div>first paint: public " + (R.timings.publicFirstPaintMs || "–") + " ms · portal's first data " + (R.timings.portalFirstDataMs || "–") + " ms</div>"
  + (R.compare ? "<div>vs " + R.compare.prevStamp + ": " + R.compare.newFindings.length + " new, " + R.compare.goneFindings.length + " gone, " + R.compare.shots.filter(s => s.status === "changed").length + " shots changed</div>" : "");
const by = {}; for (const s of R.stops) for (const c of s.checks) { const k = by[c.id] = by[c.id] || { p: 0, f: 0 }; c.ok ? k.p++ : k.f++; }
$("#tables").innerHTML = "<table><tr><th>Check</th><th>Pass</th><th>Fail</th></tr>" + Object.entries(by).map(([k, v]) => "<tr><td>" + k + "</td><td>" + v.p + "</td><td class='" + (v.f ? "fail" : "") + "'>" + v.f + "</td></tr>").join("") + "</table>"
  + (R.notes.length ? "<table><tr><th>Notes</th></tr>" + R.notes.map(n => "<tr><td>" + esc(n) + "</td></tr>").join("") + "</table>" : "");
function esc(s) { return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function draw() {
  const f = { name: $("#fPage").value, width: $("#fW").value, look: $("#fLook").value, accent: $("#fAcc").value }, onlyBad = $("#fBad").checked, orWarn = $("#fWarn").checked, chk = $("#fCheck").value;
  const rows = R.stops.filter(s => Object.entries(f).every(([k, v]) => !v || String(s[k]) === v))
    .filter(s => !chk || s.checks.some(c => c.id === chk && !c.ok) || (s.warnings || []).some(w => w.id === chk))
    .filter(s => !onlyBad || s.checks.some(c => !c.ok) || (orWarn && (s.warnings || []).length));
  $("#count").textContent = rows.length + " shown";
  $("#grid").innerHTML = rows.map(s => {
    const bad = s.checks.filter(c => !c.ok), warn = s.warnings || [];
    const cmp = R.compare && R.compare.shots.find(x => x.shot === s.shot);
    return "<div class='card'>" + (s.shot ? "<a href='" + s.shot + "' target='_blank'><img loading='lazy' src='" + s.shot + "' alt=''></a>" : "")
      + "<div class='b'><h3>" + esc(s.name) + " <span class='m'>@" + s.width + " · " + s.look + " / " + s.accent + (s.settleMs != null ? " · " + s.settleMs + " ms" : "") + (s.shotGrown ? " · shot " + s.shotGrown + " px tall" : "") + "</span></h3>"
      + (cmp && cmp.status === "changed" ? "<span class='tag warn'>changed " + cmp.pct + " %</span>" + (cmp.diff ? " <a class='m' href='" + cmp.diff + "' target='_blank'>diff</a>" : "") : "")
      + bad.map(c => "<span class='tag fail'>" + esc(c.id) + "</span>").join("") + warn.map(w => "<span class='tag warn'>" + esc(w.id) + " " + (Array.isArray(w.detail) ? w.detail.length : "") + "</span>").join("")
      + (!bad.length && !warn.length ? "<span class='tag ok'>clean</span>" : "")
      + (bad.length || warn.length || s.kind === "keyboard" ? "<details><summary>detail</summary><pre>" + esc(JSON.stringify({ checks: bad, warnings: warn, keyboard: s.stops }, null, 1)) + "</pre></details>" : "")
      + "</div></div>";
  }).join("");
}
for (const el of document.querySelectorAll("header select, header input")) el.addEventListener("change", draw);
draw();
</script></html>`;
  fs.writeFileSync(path.join(RUN_DIR, "report.html"), html);
}

// ---------------------------------------------------------------- main ------------------------------------------------
(async () => {
  let server = null, browser = null;
  const started = Date.now();
  try {
    server = await startServer({});
    console.log(`ui_audit: server ${server.base}${server.tenant ? " · tenant " + server.tenant : ""} · widths ${WIDTHS.join(",")} · looks ${LOOKS.join(",")} · accents orange${EXTRA_ACCENTS.length ? "," + EXTRA_ACCENTS.join(",") : ""}${EXTRA_PASSES.map(p => " · + " + p.look + "/" + p.accent + " at " + p.widths.join(",")).join("")}${OPT.strict44 ? " · strict 44 px" : ""} · out ${RUN_DIR}`);
    // the browser: the installed Google Chrome (the user's); Playwright's bundled Chromium only when asked or when Chrome is missing
    if (OPT.browser === "chrome") {
      try { browser = await chromium.launch({ headless: !OPT.headed, channel: "chrome" }); }
      catch (e) { note("Google Chrome did not launch (" + String(e.message || e).split("\n")[0].slice(0, 100) + "): Playwright's bundled Chromium ran instead"); }
    }
    const ranChrome = !!browser;
    if (!browser) browser = await chromium.launch({ headless: !OPT.headed });
    REPORT.browser = { asked: OPT.browser, ran: ranChrome ? "chrome" : "chromium", version: browser.version() };
    REPORT.options.browser = REPORT.browser.ran;   // what ran is the run's shape, not what was asked
    console.log(`ui_audit: browser ${REPORT.browser.ran} ${REPORT.browser.version}`);
    // the app confirms with the browser's own confirm() boxes — outside every look, axe and the screenshots; their number is on the record
    try { const src = fs.readFileSync(path.join(ROOT, "frontend", "index.html"), "utf8"); const n = (src.match(/\bconfirm\(/g) || []).length;
      REPORT.nativeConfirms = n; note(`frontend/index.html confirms with the browser's own confirm() box in ${n} places (unstyled, in no look, not pictured)`); } catch (e) {}
    let first = true;
    for (const look of LOOKS) { await walkPortal(browser, server.base, look, "orange", first, WIDTHS); first = false; }
    // the accents change the controls and the chart colours only: the desk width alone, in the first look
    for (const accent of EXTRA_ACCENTS) await walkPortal(browser, server.base, LOOKS[0], accent, false, [DESK_W]);
    // decision 15: the Dark look with the Blue accent at the desk width — the portal pages only (first = false)
    for (const p of EXTRA_PASSES) await walkPortal(browser, server.base, p.look, p.accent, false, p.widths);
    if (OPT.deep) {
      await walkTeam(browser, server.base);
      if (!server.external) { await walkLogin(browser, server.base); await walkEmpty(browser); }
      else note("login-user and empty-tenant walks need the harness's own server (not --base)");
    }
    await walkUnsigned(browser, server.base);
    if (OPT.compare) await compareRuns(browser, OPT.compare);
  } catch (e) {
    FAIL.push("the run stopped: " + (e && e.stack || e));
    console.error(e);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) await server.stop();
  }
  REPORT.totals = { passed: PASS, failed: FAIL.length };
  REPORT.failures = FAIL;
  REPORT.secs = Math.round((Date.now() - started) / 10) / 100;
  fs.writeFileSync(path.join(RUN_DIR, "report.json"), JSON.stringify(REPORT, null, 1));
  const t = summaryTables();
  writeSummaryMd(t);
  writeHtml();
  console.log("\n" + "=".repeat(64));
  for (const [k, v] of Object.entries(t.byCheck)) console.log(`${k.padEnd(22)} ${String(v.pass).padStart(5)} pass ${String(v.fail).padStart(5)} fail`);
  console.log(`warnings: ${Object.entries(t.warnBy).map(([k, v]) => k + " " + v).join(" · ") || "none"}`);
  if (t.strict44Would) console.log(`targets-44px: ${t.strict44Would} row(s) would FAIL without --no-strict-44 (not inline, not set apart)`);
  console.log(`report: ${path.join(RUN_DIR, "report.html")}  (${REPORT.secs} s; a full run is ~70 MB of screenshots — delete the runs you no longer compare against)`);
  if (FAIL.length) { console.log("\nFailures:"); for (const f of FAIL) console.log("  ✗ " + f); }
  console.log(`\n${PASS} passed, ${FAIL.length} failed`);
  process.exitCode = FAIL.length ? 1 : 0;
})();
