/*
 * ui_audit.js — the whole app in a REAL browser, every screen × width × look × accent, measured.  16 Oct 2026.
 *
 * ⚠️ NOT PART OF THE DEFAULT SUITE (run_suite.py lists it in BROWSER_ONLY). It needs:
 *   - Playwright with its Chromium and axe-core, found through NODE_PATH:
 *         npm install -g playwright axe-core ; npx playwright install chromium
 *         $env:NODE_PATH = (npm root -g)
 *   - a Python with backend/requirements.txt (the .venv-smoke of this checkout, or of ..\Modus);
 *   - a demo database (backend/forecasts_local.db, or --db). It is COPIED to a temporary folder and the
 *     server runs against the copy, so the database you point it at is never written.
 *
 *     node backend/tests/ui_audit.js                 # quick: 390 and 1366 px, Ink and Dark
 *     node backend/tests/ui_audit.js --full          # 360 390 768 1024 1366 1920 × Ink Light Dark, + the other accents at 1366
 *     node backend/tests/ui_audit.js --compare latest    # ...and say what changed since the previous run
 *     node backend/tests/ui_audit.js --base http://127.0.0.1:8834 --code <planner code> --map-password <pw>
 *
 * WHAT IT MEASURES (layer 1 of the UI review — the objective part, no judgement)
 *   at every stop (a screen at a width in a look):
 *     - no JavaScript error, no console error, no same-origin 404 / 5xx            (fail)
 *     - no sideways scroll — the document, the portal's <main>, the phone shell    (fail)
 *     - axe-core, WCAG 2.1/2.2 AA: critical and serious violations                 (fail); moderate, minor, best practice (warn)
 *     - below 768 px: every visible control at least 24 × 24 px, or set that far apart (WCAG 2.5.8)   (fail); under 44 × 44 (warn)
 *     - text smaller than 12 px, labels cut with an ellipsis                        (warn)
 *     - a screenshot of the whole screen (the portal scrolls inside <main>, so the viewport is grown to the content)
 *   once per screen, at the widest desktop width of the run, in the first look:
 *     - keyboard: Tab through the first 30 stops; each focused control must show a visible change (WCAG 2.4.7)   (fail)
 *   once per run: the time to the first paint of the public view and of the portal, and each page switch.
 *   --compare <report.json | latest>: findings new since that run / gone since; screenshots that changed (pixels
 *   compared in the browser; a diff image per changed shot).
 *
 * WHAT IT DOES NOT PROVE: nothing about whether a screen is clear, consistent or professional (layer 2, a read of
 * the shots); nothing about a real phone (Chromium's emulation); the map's tiles are Mapbox's real ones (this
 * laptop can reach them — one map load per map stop; --block-mapbox runs the map offline and counts its errors apart).
 *
 * OUTPUT  ui-audit/<stamp>/report.json · report.html (the gallery, open in a browser) · summary.md · shots/*.png
 * Count line "N passed, M failed": one assertion per check per stop.
 */
const fs = require("fs");
const os = require("os");
const net = require("net");
const http = require("http");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");
const AXE_PATH = require.resolve("axe-core/axe.min.js");

const ROOT = path.resolve(__dirname, "..", "..");
const BACKEND = path.join(ROOT, "backend");

// ---------------------------------------------------------------- options --------------------------------------------
function parseArgs(argv) {
  const o = { full: false, headed: false, blockMapbox: false, keepServer: false, out: path.join(ROOT, "ui-audit"),
              db: path.join(BACKEND, "forecasts_local.db"), python: null, base: null, code: "ui-planner",
              mapPassword: "ui-map", compare: null, widths: null, looks: null, accents: null, pages: null,
              maxShot: 4000, deep: true };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], v = () => argv[++i];
    if (a === "--full") o.full = true;
    else if (a === "--quick") o.full = false;
    else if (a === "--headed") o.headed = true;
    else if (a === "--block-mapbox") o.blockMapbox = true;
    else if (a === "--keep-server") o.keepServer = true;
    else if (a === "--no-deep") o.deep = false;
    else if (a === "--guide") o.guide = true;
    else if (a === "--out") o.out = path.resolve(v());
    else if (a === "--db") o.db = path.resolve(v());
    else if (a === "--python") o.python = v();
    else if (a === "--base") o.base = v().replace(/\/$/, "");
    else if (a === "--code") o.code = v();
    else if (a === "--map-password") o.mapPassword = v();
    else if (a === "--compare") o.compare = v();
    else if (a === "--widths") o.widths = v().split(",").map(Number);
    else if (a === "--looks") o.looks = v().split(",");
    else if (a === "--accents") o.accents = v().split(",");
    else if (a === "--pages") o.pages = v().split(",");
    else if (a === "--max-shot") o.maxShot = +v();
    else { console.error("ui_audit.js: unknown option " + a); process.exit(2); }
  }
  return o;
}
const OPT = parseArgs(process.argv.slice(2));

// the matrix. Heights are the common device heights at each width (a 390 × 844 phone, a 768 × 1024 tablet, the
// three laptop / desk sizes) — the height matters for what sits above the fold and for the phone's fixed bars.
const HEIGHT = { 360: 780, 390: 844, 768: 1024, 1024: 768, 1366: 768, 1920: 1080 };
const WIDTHS = OPT.widths || (OPT.full ? [360, 390, 768, 1024, 1366, 1920] : [390, 1366]);
const LOOKS = OPT.looks || (OPT.full ? ["ink", "light", "dark"] : ["ink", "dark"]);
const EXTRA_ACCENTS = OPT.accents || (OPT.full ? ["blue", "blue-shades", "orange-shades"] : []);
const PORTAL_PAGES = OPT.pages || ["dashboard", "submit", "forecasts", "carbon", "lookahead", "locations", "routes", "zones", "config", "users", "map"];
const DESK_W = Math.max(...WIDTHS.filter(w => w >= 1024), ...WIDTHS);   // where the deep stops and the keyboard pass run
const PHONE_W = Math.min(...WIDTHS);
const CONFIG_TABS = ["Vehicles", "Materials", "Planning", "Costing · fuel", "Seasonal restrictions", "Map and bulletin", "Everything (JSON)"];

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
async function startServer() {
  if (OPT.base) return { base: OPT.base, stop: () => {} };
  if (!fs.existsSync(OPT.db)) throw new Error("no database at " + OPT.db + " (pass --db, or copy a demo database to backend/forecasts_local.db)");
  const python = findPython();
  const port = await freePort(8834);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ui-audit-"));
  const dbCopy = path.join(tmp, "audit.db");
  fs.copyFileSync(OPT.db, dbCopy);
  // the same trick as http_smoke.py: point db at the copy BEFORE main is imported (db has no env var for its path)
  const serve = path.join(tmp, "serve.py");
  fs.writeFileSync(serve, [
    "import sys", `sys.path.insert(0, ${JSON.stringify(BACKEND)})`, "import db", `db._SQLITE_PATH = ${JSON.stringify(dbCopy)}`,
    "import main, uvicorn", `uvicorn.run(main.app, host="127.0.0.1", port=${port}, log_level="warning")`, ""].join("\n"));
  const env = { ...process.env, PYTHONUTF8: "1", ADMIN_TOKEN: "ui-audit-admin-token", PLANNER_CODE: OPT.code, ADMIN_CODE: "ui-admin",
                IPT1_CODE: "ui-team-1", MAP_PASSWORD: OPT.mapPassword, GATE_SECRET: "ui-audit-gate-secret-local-only",
                TENANT_ID: "wolds-link-demo", APP_URL: `http://127.0.0.1:${port}` };
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
  return { base, log: () => log, stop: () => { if (!OPT.keepServer) { try { proc.kill(); } catch (e) {} } else console.log("server kept at " + base); } };
}

// ---------------------------------------------------------------- the report -------------------------------------------
const STAMP = (() => { const d = new Date(), p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`; })();
const RUN_DIR = path.join(OPT.out, STAMP);
const SHOTS = path.join(RUN_DIR, "shots");
fs.mkdirSync(SHOTS, { recursive: true });

const REPORT = { stamp: STAMP, head: gitHead(), options: { full: OPT.full, widths: WIDTHS, looks: LOOKS, extraAccents: EXTRA_ACCENTS, pages: PORTAL_PAGES, blockMapbox: OPT.blockMapbox },
                 stops: [], timings: {}, totals: { passed: 0, failed: 0 } };
function gitHead() { try { return require("child_process").execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) { return null; } }

let PASS = 0;
const FAIL = [];
function ok(label, cond, extra) { if (cond) PASS++; else FAIL.push(label + (extra ? " — " + extra : "")); return !!cond; }

// ---------------------------------------------------------------- the browser-side checks --------------------------
// Runs inside the page. Everything here is plain DOM measurement; nothing is clicked.
function domChecks(arg) {
  const vis = (el) => { if (!el || !(el instanceof Element)) return false; const r = el.getBoundingClientRect(); if (!r.width && !r.height) return false;
    const cs = getComputedStyle(el); if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) return false;
    if (el.closest("details:not([open]) > :not(summary)")) return false; return true; };
  const name = (el) => (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || el.getAttribute("placeholder") || "").trim().replace(/\s+/g, " ").slice(0, 60);
  const sel = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += "#" + el.id; else if (el.className && typeof el.className === "string") s += "." + el.className.trim().split(/\s+/).slice(0, 2).join("."); return s; };
  const doc = document.documentElement;
  const main = document.querySelector("main.overflow-auto, main");
  const out = { vw: innerWidth, vh: innerHeight, theme: doc.getAttribute("data-theme"), accent: doc.getAttribute("data-accent"), title: document.title,
    docHScroll: doc.scrollWidth > innerWidth + 1 ? doc.scrollWidth - innerWidth : 0,
    mainHScroll: main && main.scrollWidth > main.clientWidth + 1 ? main.scrollWidth - main.clientWidth : 0,
    contentH: Math.max(doc.scrollHeight, main ? main.scrollHeight + main.getBoundingClientRect().top : 0),
    h1: document.querySelectorAll("h1").length, offRight: [], smallTargets: [], tinyTargets: [], smallText: [], clipped: [] };
  // what pokes out to the right (the cause of a sideways scroll, when there is one)
  if (out.docHScroll || out.mainHScroll) {
    for (const el of document.querySelectorAll("body *")) { const r = el.getBoundingClientRect();
      if (vis(el) && r.right > innerWidth + 1 && r.width < innerWidth * 3 && out.offRight.length < 12) out.offRight.push({ sel: sel(el), right: Math.round(r.right), text: name(el) }); }
  }
  // touch targets, on a phone / small tablet only. WCAG 2.5.8 (AA) wants 24 × 24, OR enough room: a 24 px circle on
  // the target's centre must not touch another target or another target's circle (the "spacing" exception; a row of
  // small dots set well apart passes). A target that is a sentence's own link is exempt too (inline). The platform
  // guides want 44 × 44, which stays a warning.
  if (arg.narrow) {
    const q = 'a[href], button, input:not([type="hidden"]), select, textarea, summary, [role="button"], [role="tab"], [role="menuitem"], [role="checkbox"], [role="switch"]';
    const all = [];
    for (const el of document.querySelectorAll(q)) {
      if (!vis(el) || el.closest(".mapboxgl-ctrl") || el.tabIndex < 0 && !el.matches("a[href], button, input, select, textarea, summary")) continue;
      const r = el.getBoundingClientRect();
      // a checkbox or radio inside its <label> counts the label (the label is the target)
      const lab = (el.type === "checkbox" || el.type === "radio") && el.closest("label") ? el.closest("label").getBoundingClientRect() : r;
      const box = { l: Math.min(r.left, lab.left), t: Math.min(r.top, lab.top), r: Math.max(r.right, lab.right), b: Math.max(r.bottom, lab.bottom) };
      const inline = el.matches("a, button") && el.parentElement && /^(P|LI|TD|SPAN|EM|STRONG|SMALL)$/.test(el.parentElement.tagName) && (el.parentElement.textContent || "").trim().length > (el.textContent || "").trim().length + 20;
      all.push({ el, box, w: Math.round(box.r - box.l), h: Math.round(box.b - box.t), inline });
    }
    const circleHits = (a, b) => {   // does a's 24 px circle touch b's box or b's circle?
      const cx = (a.box.l + a.box.r) / 2, cy = (a.box.t + a.box.b) / 2;
      const nx = Math.max(b.box.l, Math.min(cx, b.box.r)), ny = Math.max(b.box.t, Math.min(cy, b.box.b));
      if (Math.hypot(cx - nx, cy - ny) < 12) return true;
      const bx = (b.box.l + b.box.r) / 2, by = (b.box.t + b.box.b) / 2;
      return (b.w < 24 || b.h < 24) && Math.hypot(cx - bx, cy - by) < 24;
    };
    for (const a of all) {
      if (a.w >= 24 && a.h >= 24) { if (a.w < 44 || a.h < 44) out.smallTargets.push({ sel: sel(a.el), w: a.w, h: a.h, text: name(a.el) }); continue; }
      if (a.inline) continue;
      const crowded = all.some(b => b !== a && circleHits(a, b));
      const row = { sel: sel(a.el), w: a.w, h: a.h, text: name(a.el) };
      if (crowded) out.tinyTargets.push(row); else out.smallTargets.push({ ...row, spaced: true });
    }
  }
  // text under 12 px, and labels the CSS has cut with an ellipsis
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || !vis(el) || el.closest("script, style, noscript, .mapboxgl-ctrl, svg")) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize);
    const key = sel(el) + "|" + fs;
    if (fs < 12 && !seen.has(key) && out.smallText.length < 40) { seen.add(key); out.smallText.push({ sel: sel(el), px: Math.round(fs * 10) / 10, text: t.slice(0, 50) }); }
  }
  for (const el of document.querySelectorAll("*")) {
    if (out.clipped.length >= 30) break;
    const cs = getComputedStyle(el);
    if (cs.textOverflow === "ellipsis" && cs.overflow !== "visible" && vis(el) && el.scrollWidth > el.clientWidth + 1 && el.childElementCount === 0)
      out.clipped.push({ sel: sel(el), text: name(el), over: el.scrollWidth - el.clientWidth });
  }
  const nav = performance.getEntriesByType("navigation")[0];
  if (nav) out.nav = { dcl: Math.round(nav.domContentLoadedEventEnd), load: Math.round(nav.loadEventEnd) };
  return out;
}

async function runAxe(page) {
  const has = await page.evaluate(() => !!window.axe).catch(() => false);
  if (!has) await page.addScriptTag({ path: AXE_PATH });
  // Mapbox GL's own controls (.mapboxgl-ctrl: the zoom buttons, the attribution list) are left out: their markup is
  // the library's, not this app's, and axe faults its attribution list (role=list with plain children) on every map.
  const res = await page.evaluate(async () => {
    const r = await window.axe.run({ include: [["html"]], exclude: [[".mapboxgl-ctrl"]] }, { iframes: false, resultTypes: ["violations"],
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } });
    return r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, tags: v.tags.filter(t => /^wcag|best-practice/.test(t)),
      nodes: v.nodes.slice(0, 6).map(n => ({ target: n.target.join(" "), html: n.html.slice(0, 140), why: (n.any[0] || n.all[0] || n.none[0] || {}).message || "" })), count: v.nodes.length }));
  });
  return res;
}

// ---------------------------------------------------------------- settle, screenshot --------------------------------
function watch(page, store) {
  // everything the page says or fails on, drained per stop
  store.inflight = 0; store.open = [];
  const done = (r) => { store.inflight = Math.max(0, store.inflight - 1); const i = store.open.indexOf(r.url().slice(0, 100)); if (i >= 0) store.open.splice(i, 1); };
  page.on("request", r => { store.inflight++; store.open.push(r.url().slice(0, 100)); });
  page.on("requestfinished", done);
  page.on("requestfailed", r => { done(r);
    // a request the page itself cancelled (a map re-layout drops its font fetches, a navigation drops the rest) is not a failure
    const why = (r.failure() || {}).errorText || ""; if (!/ERR_ABORTED/.test(why)) store.failed.push(r.url().slice(0, 160) + " " + why); });
  page.on("framenavigated", f => { if (f === page.mainFrame()) { store.inflight = 0; store.open.length = 0; } });
  page.on("pageerror", e => store.errors.push("pageerror: " + String(e.message || e).slice(0, 300)));
  page.on("console", m => { if (m.type() === "error") store.errors.push("console: " + m.text().slice(0, 300)); });
  page.on("response", r => { const s = r.status(); if (s >= 400) store.http.push({ status: s, url: r.url().slice(0, 160) }); });
}
function drain(store) {
  const d = { errors: store.errors.splice(0), http: store.http.splice(0), failed: store.failed.splice(0) };
  return d;
}
async function settle(page, store, quiet = 700, cap = 15000) {
  // quiet = no request in flight and nothing saying "Loading…" for `quiet` ms; a stop that never gets there is
  // measured anyway after `cap`, and says why (settleWhy), so a page that keeps a request open is visible in the report
  const t0 = Date.now();
  let quietSince = null, why = "";
  while (Date.now() - t0 < cap) {
    const busy = await page.evaluate(() => {
      if (document.querySelector('[aria-busy="true"]')) return "aria-busy";
      for (const el of document.querySelectorAll("div, td, span, p")) {
        if (el.childElementCount === 0 && /^(Loading…|Signing you back in…|Loading the commit week…)$/.test(el.textContent.trim()) && el.getClientRects().length) return "loading";
      }
      return "";
    }).catch(() => "");
    why = busy || (store.inflight ? `${store.inflight} request(s) open: ${store.open.slice(0, 2).join(", ")}` : "");
    if (!busy && store.inflight === 0) { if (quietSince == null) quietSince = Date.now(); else if (Date.now() - quietSince >= quiet) { why = ""; break; } }
    else quietSince = null;
    await page.waitForTimeout(120);
  }
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))).catch(() => {});
  store.settleWhy = why;
  return Date.now() - t0;
}
async function shoot(page, file, width, height, contentH) {
  // the portal scrolls inside <main>, so fullPage would stop at the fold: grow the viewport to the content instead.
  // The big screen asks for fullscreen, and a fullscreen window cannot be resized (Chromium refuses): shot as it is.
  const full = await page.evaluate(() => !!document.fullscreenElement).catch(() => false);
  const h = full ? height : Math.min(Math.max(height, Math.ceil(contentH || 0) + 2), OPT.maxShot);
  if (h > height) { await page.setViewportSize({ width, height: h }); await page.waitForTimeout(150); }
  await page.screenshot({ path: file, fullPage: false });
  if (h > height) { await page.setViewportSize({ width, height }); await page.waitForTimeout(100); }
}
async function leaveFullscreen(page) {
  await page.evaluate(() => document.fullscreenElement && document.exitFullscreen && document.exitFullscreen()).catch(() => {});
  await page.waitForTimeout(300);
}

// ---------------------------------------------------------------- one stop -------------------------------------------
const ALLOWED_CONSOLE = [
  /status of (401|403)/,                 // the gate and the staff rules working (the public shape, /map/ before a password)
  /cdn\.tailwindcss\.com/,               // Tailwind's "not for production" note is a warning on some builds, an error on others
  /\[BABEL\] Note: The code generator has deoptimised/,   // Babel standalone on a >500 KB script: a note about ITS output's styling, printed as an error
];
const ALLOWED_HTTP = (h) => h.status === 401 || h.status === 403;

async function audit(page, store, meta) {
  const t = await settle(page, store);
  const dom = await page.evaluate(domChecks, { narrow: meta.width < 768 });
  const axe = await runAxe(page);
  const drained = drain(store);
  const file = `${meta.name}__${meta.width}__${meta.look}__${meta.accent}.png`.replace(/[^A-Za-z0-9_.+-]/g, "-");
  await shoot(page, path.join(SHOTS, file), meta.width, meta.height, dom.contentH);
  const errors = drained.errors.filter(e => !ALLOWED_CONSOLE.some(re => re.test(e)));
  const mapboxErr = OPT.blockMapbox ? errors.filter(e => /mapbox|tile|style|glyph|sprite/i.test(e)) : [];
  const realErr = errors.filter(e => !mapboxErr.includes(e));
  const http = drained.http.filter(h => !ALLOWED_HTTP(h));
  const sameOrigin = http.filter(h => h.url.startsWith(meta.base));
  const third = http.filter(h => !h.url.startsWith(meta.base) && !(OPT.blockMapbox && /mapbox/.test(h.url)));
  const axeFail = axe.filter(v => (v.impact === "critical" || v.impact === "serious") && v.tags.some(t => /^wcag/.test(t)));
  const axeWarn = axe.filter(v => !axeFail.includes(v));
  const label = `${meta.name} @${meta.width} ${meta.look}/${meta.accent}`;
  const checks = [
    { id: "no-js-errors", ok: realErr.length === 0, detail: realErr },
    { id: "no-http-errors", ok: sameOrigin.length === 0, detail: sameOrigin },
    { id: "no-sideways-scroll", ok: !dom.docHScroll && !dom.mainHScroll, detail: dom.docHScroll || dom.mainHScroll ? { doc: dom.docHScroll, main: dom.mainHScroll, offRight: dom.offRight } : null },
    { id: "axe-serious", ok: axeFail.length === 0, detail: axeFail },
  ];
  if (meta.width < 768) checks.push({ id: "targets-24px", ok: dom.tinyTargets.length === 0, detail: dom.tinyTargets });
  const warnings = [];
  if (axeWarn.length) warnings.push({ id: "axe-minor", detail: axeWarn });
  if (meta.width < 768 && dom.smallTargets.length) warnings.push({ id: "targets-44px", detail: dom.smallTargets });
  if (dom.smallText.length) warnings.push({ id: "text-under-12px", detail: dom.smallText });
  if (dom.clipped.length) warnings.push({ id: "text-clipped", detail: dom.clipped });
  if (third.length) warnings.push({ id: "third-party-http", detail: third });
  if (drained.failed.length) warnings.push({ id: "requests-failed", detail: drained.failed });
  if (mapboxErr.length) warnings.push({ id: "mapbox-offline", detail: mapboxErr });
  if (dom.h1 !== 1) warnings.push({ id: "h1-count", detail: dom.h1 });
  for (const c of checks) ok(`${label}: ${c.id}`, c.ok, c.ok ? "" : JSON.stringify(c.detail).slice(0, 300));
  const stop = { ...meta, shot: "shots/" + file, settleMs: t, settleWhy: store.settleWhy || undefined, checks, warnings, theme: dom.theme, accentApplied: dom.accent, title: dom.title, contentH: dom.contentH, nav: dom.nav };
  delete stop.base;
  REPORT.stops.push(stop);
  const bad = checks.filter(c => !c.ok).map(c => c.id);
  process.stdout.write(`${bad.length ? "FAIL" : "ok  "} ${label.padEnd(44)} ${String(t).padStart(5)} ms  ${bad.join(" ")}${warnings.length ? "  (" + warnings.map(w => w.id).join(" ") + ")" : ""}${store.settleWhy ? "  [not settled: " + store.settleWhy + "]" : ""}\n`);
  return stop;
}

// the keyboard pass: Tab through the page; each stop must be visible and must show it has the focus
async function keyboardPass(page, meta) {
  await page.evaluate(() => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); window.scrollTo(0, 0); });
  const stops = [], seen = new Set();
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const read = (e) => { const cs = getComputedStyle(e); return [cs.outlineStyle, cs.outlineWidth, cs.outlineColor, cs.boxShadow, cs.backgroundColor, cs.borderColor, cs.color, cs.textDecorationLine].join("|"); };
      const focused = read(el);
      const r = el.getBoundingClientRect();
      const inView = r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
      const key = el.tagName + "#" + el.id + "." + (el.className && el.className.baseVal === undefined ? String(el.className).split(/\s+/)[0] : "") + ":" + (el.textContent || "").trim().slice(0, 30);
      el.blur(); const blurred = read(el); el.focus({ preventScroll: true });
      const nm = (el.getAttribute("aria-label") || el.getAttribute("title") || el.textContent || el.getAttribute("placeholder") || el.value || "").trim().replace(/\s+/g, " ").slice(0, 50);
      return { key, tag: el.tagName.toLowerCase(), text: nm, inView, visibleFocus: focused !== blurred, inFrame: false, w: Math.round(r.width), h: Math.round(r.height) };
    }).catch(() => null);
    if (!info) { stops.push({ tag: "(body)", text: "", inView: true, visibleFocus: true, skipped: true }); continue; }
    if (seen.has(info.key)) break;      // wrapped round
    // the embedded map is another document: its keyboard pass is the /map/ stop's; the frame itself shows no ring
    if (info.tag === "iframe") { info.skipped = true; info.visibleFocus = true; }
    seen.add(info.key);
    stops.push(info);
  }
  const real = stops.filter(s => !s.skipped && s.w > 0 && s.h > 0);
  const noRing = real.filter(s => !s.visibleFocus);
  const hidden = real.filter(s => !s.inView);
  const label = `${meta.name} @${meta.width} ${meta.look}: keyboard`;
  ok(`${label} — every tab stop shows its focus`, noRing.length === 0, noRing.map(s => `${s.tag} "${s.text}"`).join("; ").slice(0, 300));
  ok(`${label} — every tab stop is on screen`, hidden.length === 0, hidden.map(s => `${s.tag} "${s.text}"`).join("; ").slice(0, 300));
  ok(`${label} — something takes the focus`, real.length > 0);
  REPORT.stops.push({ name: meta.name + "+keyboard", width: meta.width, height: meta.height, look: meta.look, accent: meta.accent, kind: "keyboard", stops, checks: [
    { id: "focus-visible", ok: noRing.length === 0, detail: noRing }, { id: "focus-on-screen", ok: hidden.length === 0, detail: hidden }, { id: "focus-reaches", ok: real.length > 0, detail: real.length }], warnings: [] });
  process.stdout.write(`${noRing.length || hidden.length ? "FAIL" : "ok  "} ${label.padEnd(44)}  ${real.length} stops${noRing.length ? ", " + noRing.length + " without a visible focus" : ""}${hidden.length ? ", " + hidden.length + " off screen" : ""}\n`);
}

// ---------------------------------------------------------------- the walk --------------------------------------------
async function newContext(browser, look, accent, width) {
  const ctx = await browser.newContext({ viewport: { width, height: HEIGHT[width] || 800 }, deviceScaleFactor: 1, locale: "en-GB", timezoneId: "Europe/London",
    colorScheme: look === "dark" ? "dark" : "light", isMobile: width < 768, hasTouch: width < 768 });
  // the remembered look and accent, read by the <head> script before anything draws (W16); and the demo guide's strip
  // and dots switched off (wayscope_guide_all = off, what "Hide the tips" writes) — the keyboard pass would otherwise
  // measure the tour's bubble, which takes the focus, and not the page. --guide keeps them, as a first visitor sees them.
  await ctx.addInitScript(([l, a, g]) => { try { localStorage.setItem("modus_theme", l); localStorage.setItem("modus_accent", a); if (!g) localStorage.setItem("wayscope_guide_all", "off"); } catch (e) {} }, [look, accent, OPT.guide]);
  if (OPT.blockMapbox) await ctx.route(/api\.mapbox\.com|events\.mapbox\.com|tiles\.mapbox\.com/, r => r.abort());
  return ctx;
}
async function setWidth(page, width) {
  try { await page.setViewportSize({ width, height: HEIGHT[width] || 800 }); }
  catch (e) { await leaveFullscreen(page); await page.setViewportSize({ width, height: HEIGHT[width] || 800 }); }
  await page.waitForTimeout(200);
}
async function gotoPage(page, id) {
  await page.evaluate((i) => { location.hash = "#" + i; }, id);
  await page.waitForTimeout(150);
}
async function openAllDetails(page) {
  // the folded sections only (details.dash-more), not the row menus — a menu open over the page is not a state anyone reads
  return page.evaluate(() => { let n = 0; document.querySelectorAll("details.dash-more:not([open])").forEach(d => { d.open = true; n++; }); return n; });
}
async function clickText(page, selector, text) {
  const loc = page.locator(selector).filter({ hasText: text }).first();
  if (!(await loc.count())) return false;
  await loc.click({ timeout: 5000 }).catch(() => {});
  return true;
}

async function walkPortal(browser, base, look, accent, first, WIDTHS) {
  const ctx = await newContext(browser, look, accent, DESK_W);
  const page = await ctx.newPage();
  const store = { errors: [], http: [], failed: [] };
  watch(page, store);
  const meta = (name, width, extra) => ({ name, width, height: HEIGHT[width] || 800, look, accent, base, ...(extra || {}) });

  // 1. the public view, the sign-in screens — at every width, only in the first look+accent (they do not change with the page's data)
  const t0 = Date.now();
  await page.goto(base + "/", { waitUntil: "domcontentloaded" });
  await page.waitForSelector('button:has-text("Staff sign in"), [data-guide="rail"]', { timeout: 60000 });
  if (first) REPORT.timings.publicFirstPaintMs = Date.now() - t0;
  if (first) {
    for (const w of WIDTHS) { await setWidth(page, w); await audit(page, store, meta("public", w)); }
    await setWidth(page, DESK_W);
    await page.getByRole("button", { name: "Staff sign in" }).click();
    await page.waitForSelector("#auth-email");
    for (const w of WIDTHS) { await setWidth(page, w); await audit(page, store, meta("login", w)); }
    if (OPT.deep) { await setWidth(page, DESK_W); await keyboardPass(page, meta("login", DESK_W)); }
    await page.getByRole("button", { name: "Sign in with a team code instead" }).click({ timeout: 15000 });
    await page.waitForSelector("#auth-code");
    for (const w of WIDTHS) { await setWidth(page, w); await audit(page, store, meta("login-code", w)); }
    await setWidth(page, DESK_W);
  } else {
    await page.getByRole("button", { name: "Staff sign in" }).click();
    await page.getByRole("button", { name: "Sign in with a team code instead" }).click({ timeout: 15000 });
  }
  // 2. sign in with the planner code (sees every page; Users shows to a code with can_approve)
  await page.fill("#auth-name", "UI audit");
  await page.fill("#auth-code", OPT.code);
  const t1 = Date.now();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.waitForSelector('[data-guide="rail"]', { timeout: 60000 });
  if (first) REPORT.timings.portalFirstPaintMs = Date.now() - t1;
  drain(store);

  // 3. every portal page at every width
  const switches = [];
  for (const w of WIDTHS) {
    await setWidth(page, w);
    for (const id of PORTAL_PAGES) {
      const ts = Date.now();
      await gotoPage(page, id);
      const s = await audit(page, store, meta(id, w));
      if (w === DESK_W && first) switches.push({ page: id, ms: Date.now() - ts });
      // the deep stops: once, at the desk width, in the first look+accent
      if (OPT.deep && w === DESK_W && first) {
        await keyboardPass(page, meta(id, w));
        if (id === "dashboard") {
          if (await openAllDetails(page)) await audit(page, store, meta("dashboard+open", w));
          if (await clickText(page, '[data-guide="dash-wall"]', "Big screen")) {
            await audit(page, store, meta("dashboard-bigscreen", w));
            await page.keyboard.press("Escape"); await page.waitForTimeout(300); await leaveFullscreen(page);
            if (await page.locator('[data-guide="dash-wall"]').filter({ hasText: "Exit big screen" }).count()) await clickText(page, '[data-guide="dash-wall"]', "Exit big screen");
          }
        }
        if (id === "carbon" && await openAllDetails(page)) await audit(page, store, meta("carbon+open", w));
        if (id === "lookahead") {
          for (const [k, t] of [["account", "Account"], ["horizon", "Horizon"]]) if (await clickText(page, '[data-guide="lookahead-tabs"] button', t)) await audit(page, store, meta("lookahead-" + k, w));
          await clickText(page, '[data-guide="lookahead-tabs"] button', "Commit");
        }
        if (id === "config") {
          for (const t of CONFIG_TABS.slice(1)) if (await clickText(page, ".cfg-nav-item", t)) await audit(page, store, meta("config-" + t.toLowerCase().replace(/[^a-z]+/g, "-").replace(/-$/, ""), w));
          await clickText(page, ".cfg-nav-item", CONFIG_TABS[0]);
        }
      }
      // the phone's More sheet, once, at the narrowest width
      if (w === PHONE_W && w < 768 && id === "dashboard" && first) {
        if (await clickText(page, ".phone-tabs button", "More")) { await audit(page, store, meta("phone-more", w)); await page.keyboard.press("Escape"); await page.waitForTimeout(300); }
      }
    }
  }
  if (first) REPORT.timings.pageSwitches = switches;

  // 4. the public map on its own (the staff cookie opens it), and the staff-only documents
  for (const w of WIDTHS) {
    await setWidth(page, w);
    await page.goto(base + "/map/", { waitUntil: "domcontentloaded" });
    await waitForMap(page);
    await audit(page, store, meta("map-page", w));
    if (w === PHONE_W && w < 768 && first && await page.locator("#menu-toggle").isVisible().catch(() => false)) {
      await page.locator("#menu-toggle").click(); await page.waitForTimeout(400);
      await audit(page, store, meta("map-page-menu", w));
    }
  }
  if (first) {
    const month = await page.evaluate(async () => { const m = await (await fetch("/api/meta")).json(); const d = new Date(); const sy = m && m.months && m.months.start_year;
      return sy ? (d.getFullYear() - sy) * 12 + d.getMonth() + 1 : 10; }).catch(() => 10);
    REPORT.month = month;
    const docs = [["help", "/help/"], ["help-technical", "/help/technical/"], ["bulletin", "/bulletin/?month=" + month], ["bulletin-leaflet", "/bulletin/leaflet/?month=" + month]];
    for (const [name, url] of docs) for (const w of WIDTHS) {
      await setWidth(page, w);
      await page.goto(base + url, { waitUntil: "domcontentloaded" });
      await audit(page, store, meta(name, w));
      if (OPT.deep && w === DESK_W) await keyboardPass(page, meta(name, w));
    }
  }
  await ctx.close();
}
async function waitForMap(page) {
  // the map is a top-level `let` in a classic script: visible to evaluate by name, not as window.map
  const t0 = Date.now();
  while (Date.now() - t0 < 30000) {
    const st = await page.evaluate(() => { try { return (typeof map !== "undefined" && map && map.loaded && map.loaded()) ? "loaded" : (document.querySelector("#p") ? "password" : "loading"); } catch (e) { return "error:" + e.message; } }).catch(() => "nav");
    if (st === "loaded" || st === "password" || st.startsWith("error")) return st;
    await page.waitForTimeout(300);
  }
  return "timeout";
}
async function walkUnsigned(browser, base) {
  // a visitor without any cookie: the map's password page
  const ctx = await newContext(browser, LOOKS[0], "orange", DESK_W);
  const page = await ctx.newPage();
  const store = { errors: [], http: [], failed: [] };
  watch(page, store);
  for (const w of WIDTHS) {
    await setWidth(page, w);
    await page.goto(base + "/map/", { waitUntil: "domcontentloaded" });
    await audit(page, store, { name: "map-password", width: w, height: HEIGHT[w] || 800, look: LOOKS[0], accent: "orange", base });
  }
  if (OPT.deep) { await setWidth(page, DESK_W); await keyboardPass(page, { name: "map-password", width: DESK_W, height: HEIGHT[DESK_W], look: LOOKS[0], accent: "orange" }); }
  // the wrong password, then the right one — the map opens with the map cookie alone
  await page.fill("#p", "not-the-password"); await page.click('#f button[type="submit"]'); await page.waitForTimeout(600);
  await audit(page, store, { name: "map-password-wrong", width: DESK_W, height: HEIGHT[DESK_W], look: LOOKS[0], accent: "orange", base });
  await page.fill("#p", OPT.mapPassword); await page.click('#f button[type="submit"]');
  await page.waitForTimeout(1500);
  const st = await waitForMap(page);
  ok("the map password opens the public map (the map cookie alone)", st === "loaded", st);
  await audit(page, store, { name: "map-public", width: DESK_W, height: HEIGHT[DESK_W], look: LOOKS[0], accent: "orange", base });
  await ctx.close();
}

// ---------------------------------------------------------------- compare with an earlier run -------------------------
function findingKeys(stop) {
  const keys = [];
  for (const c of (stop.checks || [])) if (!c.ok) {
    const d = Array.isArray(c.detail) ? c.detail : [c.detail];
    for (const x of d) keys.push(`${stop.name}|${stop.width}|${stop.look}|${stop.accent}|${c.id}|${x && (x.id || x.sel || x.url || x.key) ? (x.id || x.sel || x.url || x.key) : JSON.stringify(x).slice(0, 80)}`);
  }
  for (const w of (stop.warnings || [])) {
    const d = Array.isArray(w.detail) ? w.detail : [w.detail];
    for (const x of d) keys.push(`${stop.name}|${stop.width}|${stop.look}|${stop.accent}|${w.id}|${x && (x.id || x.sel || x.url) ? (x.id || x.sel || x.url) : JSON.stringify(x).slice(0, 80)}`);
  }
  return keys;
}
async function compareRuns(browser, prevPath) {
  if (prevPath === "latest") {
    const runs = fs.readdirSync(OPT.out).filter(d => d !== STAMP && fs.existsSync(path.join(OPT.out, d, "report.json"))).sort();
    if (!runs.length) { console.log("compare: no earlier run in " + OPT.out); return null; }
    prevPath = path.join(OPT.out, runs[runs.length - 1], "report.json");
  }
  const prev = JSON.parse(fs.readFileSync(prevPath, "utf8"));
  const prevDir = path.dirname(prevPath);
  const now = new Set(REPORT.stops.flatMap(findingKeys)), was = new Set(prev.stops.flatMap(findingKeys));
  const diff = { against: prevPath, prevStamp: prev.stamp, prevHead: prev.head, newFindings: [...now].filter(k => !was.has(k)), goneFindings: [...was].filter(k => !now.has(k)), shots: [] };
  // pixels, compared in the browser (Chromium decodes the PNGs; no image package needed)
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
    const r = await page.evaluate(async ([A, B]) => {
      const load = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
      const [ia, ib] = await Promise.all([load(A), load(B)]);
      const w = Math.max(ia.width, ib.width), h = Math.max(ia.height, ib.height);
      const cv = (img) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(img, 0, 0); return g.getImageData(0, 0, w, h).data; };
      const da = cv(ia), db = cv(ib);
      const out = document.createElement("canvas"); out.width = w; out.height = h; const g = out.getContext("2d"); const od = g.createImageData(w, h);
      let n = 0;
      for (let i = 0; i < da.length; i += 4) {
        const d = Math.abs(da[i] - db[i]) + Math.abs(da[i + 1] - db[i + 1]) + Math.abs(da[i + 2] - db[i + 2]);
        const changed = d > 48; if (changed) n++;
        od.data[i] = changed ? 220 : Math.round(da[i] * 0.25 + 190); od.data[i + 1] = changed ? 30 : Math.round(da[i + 1] * 0.25 + 190); od.data[i + 2] = changed ? 30 : Math.round(da[i + 2] * 0.25 + 190); od.data[i + 3] = 255;
      }
      g.putImageData(od, 0, 0);
      const pct = Math.round(n * 10000 / (w * h)) / 100;
      return { pct, sizeChanged: ia.width !== ib.width || ia.height !== ib.height, png: pct > 0.5 ? out.toDataURL("image/png") : null };
    }, ["data:image/png;base64," + fs.readFileSync(a).toString("base64"), "data:image/png;base64," + fs.readFileSync(b).toString("base64")]);
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
  for (const s of REPORT.stops) for (const c of s.checks) if (c.id === "axe-serious" && !c.ok) for (const v of c.detail) { const k = axeBy[v.id] = axeBy[v.id] || { impact: v.impact, help: v.help, stops: 0, nodes: 0, where: new Set() }; k.stops++; k.nodes += v.count; k.where.add(s.name); }
  for (const s of REPORT.stops) for (const w of s.warnings || []) if (w.id === "axe-minor") for (const v of w.detail) { const k = axeBy[v.id] = axeBy[v.id] || { impact: v.impact, help: v.help, stops: 0, nodes: 0, where: new Set() }; k.stops++; k.nodes += v.count; k.where.add(s.name); }
  return { byCheck, warnBy, axeBy: Object.fromEntries(Object.entries(axeBy).map(([k, v]) => [k, { ...v, where: [...v.where] }])) };
}
function writeSummaryMd(t) {
  const lines = [`# UI audit ${REPORT.stamp} — ${REPORT.head || "?"}`, "",
    `${REPORT.stops.length} stops · widths ${WIDTHS.join(", ")} · looks ${LOOKS.join(", ")}${EXTRA_ACCENTS.length ? " · accents " + EXTRA_ACCENTS.join(", ") + " at 1366" : ""}`,
    `**${PASS} passed, ${FAIL.length} failed.** First paint: public ${REPORT.timings.publicFirstPaintMs} ms, portal after sign-in ${REPORT.timings.portalFirstPaintMs} ms.`, "",
    "## Checks (one per stop)", "", "| Check | Pass | Fail | Failing widths |", "|---|---:|---:|---|"];
  for (const [k, v] of Object.entries(t.byCheck)) lines.push(`| ${k} | ${v.pass} | ${v.fail} | ${Object.entries(v.widths).map(([w, n]) => w + " (" + n + ")").join(", ")} |`);
  lines.push("", "## Warnings (not counted as failures)", "", "| Warning | Items across all stops |", "|---|---:|");
  for (const [k, v] of Object.entries(t.warnBy)) lines.push(`| ${k} | ${v} |`);
  lines.push("", "## axe rules hit", "", "| Rule | Impact | Stops | Nodes | Screens |", "|---|---|---:|---:|---|");
  for (const [k, v] of Object.entries(t.axeBy).sort((a, b) => b[1].stops - a[1].stops)) lines.push(`| ${k} | ${v.impact} | ${v.stops} | ${v.nodes} | ${v.where.slice(0, 8).join(", ")}${v.where.length > 8 ? " …" : ""} |`);
  if (REPORT.timings.pageSwitches) { lines.push("", "## Page switches at " + DESK_W + " px (first look)", "", "| Page | ms |", "|---|---:|"); for (const p of REPORT.timings.pageSwitches) lines.push(`| ${p.page} | ${p.ms} |`); }
  if (FAIL.length) { lines.push("", "## Failures", ""); for (const f of FAIL) lines.push("- " + f); }
  if (REPORT.compare) { const c = REPORT.compare; lines.push("", `## Compared with ${c.prevStamp} (${c.prevHead})`, "", `${c.newFindings.length} new, ${c.goneFindings.length} gone, ${c.shots.filter(s => s.status === "changed").length} screenshots changed`);
    for (const k of c.newFindings) lines.push("- new: " + k); for (const k of c.goneFindings) lines.push("- gone: " + k); for (const s of c.shots.filter(s => s.status === "changed")) lines.push(`- changed ${s.pct} %: ${s.shot}`); }
  fs.writeFileSync(path.join(RUN_DIR, "summary.md"), lines.join("\n") + "\n");
}
function writeHtml() {
  const json = JSON.stringify(REPORT).replace(/<\//g, "<\\/");
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
$("#sum").innerHTML = "<div><b>" + R.totals.passed + "</b> passed · <b class='" + (R.totals.failed ? "fail" : "ok") + "'>" + R.totals.failed + "</b> failed</div>"
  + "<div>" + R.stops.length + " stops</div><div>first paint: public " + (R.timings.publicFirstPaintMs || "–") + " ms · portal " + (R.timings.portalFirstPaintMs || "–") + " ms</div>"
  + (R.compare ? "<div>vs " + R.compare.prevStamp + ": " + R.compare.newFindings.length + " new, " + R.compare.goneFindings.length + " gone, " + R.compare.shots.filter(s => s.status === "changed").length + " shots changed</div>" : "");
const by = {}; for (const s of R.stops) for (const c of s.checks) { const k = by[c.id] = by[c.id] || { p: 0, f: 0 }; c.ok ? k.p++ : k.f++; }
$("#tables").innerHTML = "<table><tr><th>Check</th><th>Pass</th><th>Fail</th></tr>" + Object.entries(by).map(([k, v]) => "<tr><td>" + k + "</td><td>" + v.p + "</td><td class='" + (v.f ? "fail" : "") + "'>" + v.f + "</td></tr>").join("") + "</table>";
function esc(s) { return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function draw() {
  const f = { name: $("#fPage").value, width: $("#fW").value, look: $("#fLook").value, accent: $("#fAcc").value }, onlyBad = $("#fBad").checked, orWarn = $("#fWarn").checked;
  const rows = R.stops.filter(s => Object.entries(f).every(([k, v]) => !v || String(s[k]) === v)).filter(s => !onlyBad || s.checks.some(c => !c.ok) || (orWarn && (s.warnings || []).length));
  $("#count").textContent = rows.length + " shown";
  $("#grid").innerHTML = rows.map(s => {
    const bad = s.checks.filter(c => !c.ok), warn = s.warnings || [];
    const cmp = R.compare && R.compare.shots.find(x => x.shot === s.shot);
    return "<div class='card'>" + (s.shot ? "<a href='" + s.shot + "' target='_blank'><img loading='lazy' src='" + s.shot + "' alt=''></a>" : "")
      + "<div class='b'><h3>" + esc(s.name) + " <span class='m'>@" + s.width + " · " + s.look + " / " + s.accent + (s.settleMs != null ? " · " + s.settleMs + " ms" : "") + "</span></h3>"
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
    server = await startServer();
    console.log(`ui_audit: server ${server.base} · widths ${WIDTHS.join(",")} · looks ${LOOKS.join(",")} · accents orange${EXTRA_ACCENTS.length ? "," + EXTRA_ACCENTS.join(",") : ""} · out ${RUN_DIR}`);
    browser = await chromium.launch({ headless: !OPT.headed });
    let first = true;
    for (const look of LOOKS) { await walkPortal(browser, server.base, look, "orange", first, WIDTHS); first = false; }
    // the accents change the controls and the chart colours only: the desk width alone, in the first look
    for (const accent of EXTRA_ACCENTS) await walkPortal(browser, server.base, LOOKS[0], accent, false, [DESK_W]);
    await walkUnsigned(browser, server.base);
    if (OPT.compare) await compareRuns(browser, OPT.compare);
  } catch (e) {
    FAIL.push("the run stopped: " + (e && e.stack || e));
    console.error(e);
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (server) server.stop();
  }
  REPORT.totals = { passed: PASS, failed: FAIL.length };
  REPORT.secs = Math.round((Date.now() - started) / 10) / 100;
  fs.writeFileSync(path.join(RUN_DIR, "report.json"), JSON.stringify(REPORT, null, 1));
  const t = summaryTables();
  writeSummaryMd(t);
  writeHtml();
  console.log("\n" + "=".repeat(64));
  for (const [k, v] of Object.entries(t.byCheck)) console.log(`${k.padEnd(22)} ${String(v.pass).padStart(5)} pass ${String(v.fail).padStart(5)} fail`);
  console.log(`warnings: ${Object.entries(t.warnBy).map(([k, v]) => k + " " + v).join(" · ") || "none"}`);
  console.log(`report: ${path.join(RUN_DIR, "report.html")}  (${REPORT.secs} s)`);
  if (FAIL.length) { console.log("\nFailures:"); for (const f of FAIL) console.log("  ✗ " + f); }
  console.log(`\n${PASS} passed, ${FAIL.length} failed`);
  process.exit(FAIL.length ? 1 : 0);
})();
