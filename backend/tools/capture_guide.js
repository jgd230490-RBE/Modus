/*
 * tools/capture_guide.js — the user guide's real screenshots, captured from a running
 * deployment. Wayscope (G2, 16 Sep 2026; rewritten 11 Oct 2026 for guide v2.1).
 *
 * THE COMMAND (PowerShell, in the repository's folder, the git clone, on a branch — never on main):
 *
 *     $env:MODUS_URL = "https://app.wayscope.co.uk"
 *     $env:MODUS_PLANNER_CODE = Read-Host "Planner code"     # typed at the prompt, kept out of the history
 *     $env:NODE_PATH = (npm root -g)
 *     Remove-Item Env:MODUS_ONLY, Env:MODUS_SKIP, Env:MODUS_OUT -ErrorAction SilentlyContinue   # no leftovers
 *     node backend/tools/capture_guide.js
 *
 *   Needs Playwright and its Chromium, installed once: npm i -g playwright; npx playwright install chromium
 *   Takes about four minutes. To retake some shots only, first:  $env:MODUS_ONLY = "M02,M05"
 *   (Remove-Item Env:MODUS_ONLY to go back to all). $env:MODUS_OUT = "<folder>" writes somewhere
 *   else: a dry run that must not replace the committed pictures.
 *   MODUS_SKIP — a comma list of pictures NOT taken (their placeholders stay); default "S14". S14 is
 *   Config › Vehicles, and the live demo still lists the EU vehicles there until the branch that removes
 *   them (claude/remove-eu-vehicles) merges after the show; then take it alone with $env:MODUS_ONLY = "S14"
 *   (MODUS_ONLY wins over MODUS_SKIP). $env:MODUS_SKIP = "none" skips nothing.
 *
 * THE BROWSER it drives is its own, told it is in Britain (locale en-GB, Europe/London time, --lang=en-GB)
 * whatever this laptop's regional settings are, so the pictures read 16.1 t and 01/09/2026. It asks for the GPU
 * (--enable-gpu, --use-angle=d3d11): headless Chromium's software renderer, SwiftShader, leaves a blank
 * strip at the foot of the map, and a map shot whose foot is blank fails rather than be saved.
 *
 * WHAT IT WRITES: frontend/help/media/S01.png … S17.png and M01.png … M08.png (there is no M04),
 * 1440 × 760 each, over the placeholders. A shot that fails is reported and its file is NOT
 * touched, so the guide never shows a broken image; the run then ends with exit code 1 and the
 * list of what failed. Look at every new picture before committing it (git diff shows which
 * changed); commit them on a branch.
 *
 * It signs in with the PLANNER code (the guide's screens are the planner's view) and walks every
 * page the guide shows. The in-app tour strip and its dots are switched off in its own throwaway
 * browser only (localStorage), so the pictures show the screens, not the tour.
 *
 * 🔴 IT NEVER CONFIRMS, APPROVES, BAKES, SETS OR SAVES ANYTHING.
 *    - Every request to the API other than a GET is ABORTED, except the three reads that take a
 *      body: /api/auth (sign-in), /api/costing/preview and /api/carbon/scenario. A blocked write
 *      is listed at the end and fails the run.
 *    - Every confirm() the app asks is answered No.
 *    - The Confirm week dialog (S10) is opened with the header's button, found by its title, and
 *      closed with the dialog's Cancel; the dialog's own Confirm week button is never touched.
 *    - Submit forecast (S04) loads an existing approved line and never presses Save; no figure is
 *      typed. The Look-ahead's day cells are never clicked (a click opens a cell that saves on blur).
 *    What it does spend, as any visitor would: opening the Look-ahead creates the commit week's
 *    days on demand; S10 opens NEXT week only if this week is already confirmed; S15 exports the
 *    week PDF once (its route map is a Mapbox Static Images call); M05 has the server read
 *    National Highways' closures (cached 30 min); M08 asks the free Street View metadata first and
 *    then fetches ONE picture (a billable Google request) for the first site that has imagery.
 *
 * Shots that can fail for a reason that is not the script's (each failure says which):
 *   M02, M05 — 11 Oct 2026: may fail and keep their placeholders until the public map's bugs (the alignment click throws, closures and zones are not drawn) are fixed; then retake them with MODUS_ONLY.
 *   M08 — needs GOOGLE_MAPS_API_KEY on the server and a site with Street View imagery within
 *         50 m. Neither → fails and the placeholder stays.
 *   S15 — renders page 1 of the week PDF: with poppler's pdftoppm where installed, otherwise in the
 *         same Chromium with pdf.js 3.11.174 from cdnjs (this laptop has no poppler).
 *
 * History: written 16 Sep 2026 and never run against a deployment. 11 Oct 2026: every shot checked
 * against today's UI (the demo bar since PR #27, the carbon-target strip, the Carbon planner, the
 * Look-ahead's ▶ rows and remembered view, the folded Layers and basemap) and dry-run against a
 * LOCAL copy of the demo (MODUS_OUT in the scratchpad), never against the live site. 11 Oct 2026, after the
 * review: the GPU launch and the blank-foot check on the map, en-GB and London time, S12 checked to hold the
 * analysis table, S15 drawn at the size shown, S05 with the rail folded, S08's caption to what it shows,
 * MODUS_SKIP (S14 by default). Dry-run again against the local copy only.
 *
 * MODUS_LOCAL_LIBS=<dir>  (a test aid for machines without CDN access) serves React, ReactDOM,
 *    Babel, Chart.js and mapbox-gl from <dir>/node_modules and a prebuilt <dir>/tw.css in place
 *    of the Tailwind CDN. Map tiles still need Mapbox, so the M shots fail in that mode.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

// every picture the guide shows, in the order they are taken (M04 does not exist)
const SHOTS = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14",
               "S16", "S17", "S15", "M01", "M02", "M03", "M05", "M06", "M07", "M08"];

// the refusals come before Playwright is loaded: a refusal needs no browser
const BASE = (process.env.MODUS_URL || "").trim().replace(/\/+$/, "");
const CODE = (process.env.MODUS_PLANNER_CODE || "").trim();
if (!BASE || !CODE) {
  console.error("Set MODUS_URL and MODUS_PLANNER_CODE first (the command is at the top of this file).");
  process.exit(2);
}
if (!/^https?:\/\/[^/]+$/.test(BASE)) {
  console.error(`MODUS_URL must be the site address only, e.g. https://app.wayscope.co.uk (got ${BASE}).`);
  process.exit(2);
}
const ONLY = (process.env.MODUS_ONLY || "").split(",").map(s => s.trim()).filter(Boolean);
if (ONLY.some(id => !SHOTS.includes(id))) {
  console.error(`MODUS_ONLY names a picture the guide does not have: ${ONLY.filter(id => !SHOTS.includes(id)).join(", ")}.`);
  process.exit(2);
}
// MODUS_SKIP: pictures not taken (their placeholders stay). Default S14: the live Config › Vehicles still lists the
// EU vehicles until claude/remove-eu-vehicles merges. "none" skips nothing; MODUS_ONLY wins over it.
const SKIP_RAW = process.env.MODUS_SKIP === undefined ? "S14" : process.env.MODUS_SKIP;
const SKIP = /^\s*none\s*$/i.test(SKIP_RAW) ? [] : SKIP_RAW.split(",").map(s => s.trim()).filter(Boolean);
if (SKIP.some(id => !SHOTS.includes(id))) {
  console.error(`MODUS_SKIP names a picture the guide does not have: ${SKIP.filter(id => !SHOTS.includes(id)).join(", ")}.`);
  process.exit(2);
}
const { chromium } = require("playwright");

const WHO = process.env.MODUS_NAME || "Guide capture";
// MODUS_OUT writes somewhere else (a dry run that must not replace the committed images)
const MEDIA = process.env.MODUS_OUT || path.resolve(__dirname, "..", "..", "frontend", "help", "media");
// the only API calls other than GET that may leave this browser: reads that take a body
const READS_WITH_A_BODY = ["/api/auth", "/api/costing/preview", "/api/carbon/scenario"];
const PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
const PDFJS_WORKER = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

const VIEW = { width: 1440, height: 760 };
const TOP = 92;            // the sticky header (66 px) and the demo bar (26 px) cover the page under them
// 11 Oct 2026: the browser is British whatever this laptop's regional settings (an Estonian laptop gave 16,1 t). The
// context's locale sets JavaScript's figures and dates; a date box (<input type="date">, S13's From/To) is drawn by
// Chromium in the operating system's regional format (01.09.2026) unless Chromium itself starts with --lang=en-GB.
const LOCALE = { locale: "en-GB", timezoneId: "Europe/London" };
const LANG_ARGS = ["--lang=en-GB"];
// 11 Oct 2026: the map is WebGL, and headless Chromium's software renderer (SwiftShader) left a blank strip ~100 px
// tall at the foot of every map picture. With the GPU it draws to the foot; without one, the plain launch is used and
// mapReady() fails a map shot whose foot is blank rather than save it.
const GPU_ARGS = ["--enable-gpu", "--use-angle=d3d11", "--ignore-gpu-blocklist"];
const done = [], failed = [], skipped = [], blocked = [];
const want = (id) => ONLY.length ? ONLY.includes(id) : !SKIP.includes(id);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const first = (s) => String((s && s.message) || s).split("\n")[0];

async function shot(page, id, fn) {
  if (!want(id)) return;
  try {
    const before = blocked.length;
    await fn();
    if (blocked.length > before) throw new Error(`the page tried to write: ${blocked.slice(before).join("; ")}`);
    // a map picture is taken by the foot check itself and saved only if its foot is drawn
    if (id.startsWith("M")) fs.writeFileSync(path.join(MEDIA, id + ".png"), await mapFootDrawn(page));
    else await page.screenshot({ path: path.join(MEDIA, id + ".png"), clip: { x: 0, y: 0, ...VIEW } });
    done.push(id);
    console.log("  ✓", id);
  } catch (e) {
    failed.push(`${id}: ${first(e)}`);
    console.log("  ✗", id, "—", first(e));
  }
}

// ---- the staff app ---------------------------------------------------------------------
// The page scrolls inside <main> (under the header and the demo bar), not the window. The app routes on the
// hash, so a page change is a same-page move and <main> keeps its scroll: hence the reset.
async function toTop(page) {
  await page.evaluate(() => { const m = document.querySelector("main"); if (m) m.scrollTop = 0; window.scrollTo(0, 0); });
}
async function goApp(page, hash, title) {
  await page.evaluate((h) => { window.location.hash = h; }, hash);
  await page.locator("h2", { hasText: new RegExp("^" + title + "$") }).first().waitFor({ timeout: 20000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  await toTop(page);
  await sleep(1500);
}
// put an element's top `gap` px below the top of the area that scrolls it (under the header and demo bar),
// through every scrolling box it sits in, innermost first (a table can scroll inside <main>)
async function scrollUnderHeader(page, locator, gap = 12) {
  await locator.waitFor({ timeout: 15000 });
  await locator.evaluate((el, [g, top]) => {
    let any = false;
    for (let s = el.parentElement; s; s = s.parentElement) {
      if (!(s.scrollHeight > s.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(s).overflowY))) continue;
      // <main> starts under the header, and the demo bar lies over its top: count from below both
      s.scrollTop += el.getBoundingClientRect().top - Math.max(s.getBoundingClientRect().top, top) - g;
      any = true;
    }
    if (!any) window.scrollBy(0, el.getBoundingClientRect().top - top - g);
  }, [gap, TOP]);
  await sleep(900);
}
// the Look-ahead: pick the view and the week explicitly — the page remembers the view last used
async function lookahead(page, view, bucket = "this week") {
  await goApp(page, "lookahead", "Look-ahead");
  await page.getByRole("button", { name: bucket, exact: true }).click({ timeout: 8000 });
  await page.getByRole("button", { name: view === "commit" ? /^Commit · / : view, exact: view !== "commit" }).first().click({ timeout: 8000 });
  await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(1800);
}
// the header's Confirm button, found by its title: the dialog's own Confirm week has none
const HEADER_CONFIRM = 'button[title^="Whole week, every line, one act"]';
const confirmDialog = (page) => page.locator("div.fixed.inset-0", { hasText: "Confirm the week of" });
async function cancelConfirmDialog(page) {
  const dlg = confirmDialog(page);
  if (!(await dlg.count())) return;
  await dlg.getByRole("button", { name: "Cancel", exact: true }).click({ timeout: 5000 });
  await dlg.waitFor({ state: "detached", timeout: 5000 });
}
// the data pages: the map and the form side by side; the form column scrolls inside
async function dataPage(page, hash, title, rowText, fallbackType) {
  await goApp(page, hash, title);
  let row = page.locator("tbody tr", { hasText: rowText }).first();
  if (!(await row.count()) && fallbackType) row = page.locator("tbody tr", { hasText: fallbackType }).first();
  await row.scrollIntoViewIfNeeded({ timeout: 8000 });
  await row.click({ timeout: 8000 });        // locates it on the map and opens it in the form; nothing is saved
  await sleep(2500);
}
// the rail (the list of pages on the left) folded or opened with its own button; this browser remembers the choice
// (localStorage), so a fold is always undone by the caller
async function setRail(page, open) {
  const btn = page.locator(`aside[data-guide="rail"] button[title="${open ? "Expand" : "Collapse"}"]`).first();
  if (!(await btn.count())) return;          // already as asked
  await btn.click({ timeout: 5000 });
  await sleep(700);
}
async function showGridTop(page) {
  await scrollUnderHeader(page, page.locator("div.grid.gap-4").first(), 8);
}
async function scrollPanelTo(page, text) {
  await page.evaluate((t) => {
    const lab = [...document.querySelectorAll("span,div,label")].find(e => e.children.length === 0 && e.textContent.trim().startsWith(t));
    if (!lab) return;
    let p = lab.parentElement;
    while (p && !(p.scrollHeight > p.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(p).overflowY))) p = p.parentElement;
    if (p) p.scrollTop += lab.getBoundingClientRect().top - p.getBoundingClientRect().top - 24;
  }, text);
  await sleep(700);
}

// ---- the public map: evaluate against the page's own `map` ------------------------------
async function mapReady(page) {
  await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded()
    && window.alignment_data && typeof a1_data !== "undefined", null, { timeout: 45000 });
  await sleep(2500);
  if (!RENDERER) {       // said once: what drew the map (a "SwiftShader" here means no GPU)
    RENDERER = await page.evaluate(() => { try { const gl = map.painter.context.gl, x = gl.getExtension("WEBGL_debug_renderer_info");
      return x ? gl.getParameter(x.UNMASKED_RENDERER_WEBGL) : "unknown"; } catch (e) { return "unknown"; } });
    console.log("  (the map is drawn by " + RENDERER + ")");
  }
  await mapFootDrawn(page);
}
let RENDERER = "";
// 11 Oct 2026: the map's foot is drawn, or the shot fails. The map canvas must reach the foot of the window; the whole
// picture is taken, and a strip of FOOT_ROWS rows just above the foot, where the canvas itself is on top (clear of the
// logo, the basemap buttons, the attribution and the timeline), is read back from it: blank is (nearly) every row one
// flat colour, which is what the software renderer left (a white-to-grey band ~100 px tall); a drawn map varies along
// every row. It must be the WHOLE picture: without the GPU a small clip of the same strip came out drawn while the
// full-window picture had the band. Checked when the map is ready, and as each map picture is taken: the picture
// returned is the one checked, and the one saved.
const FOOT_ROWS = 20;
async function mapFootDrawn(page) {
  let last = "";
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt) { await page.evaluate(() => map.triggerRepaint()); await sleep(1500); }
    const seg = await page.evaluate((rows) => {
      const cv = map.getCanvas(), b = cv.getBoundingClientRect(), H = window.innerHeight;
      if (b.bottom < H - 2) return { short: true, bottom: Math.round(b.bottom), H };
      const y0 = Math.round(H - 30 - rows), ys = [y0, y0 + Math.floor(rows / 2), y0 + rows - 1];
      let best = null, run = null;
      for (let x = Math.ceil(b.left) + 2; x < Math.min(b.right, window.innerWidth) - 2; x += 4) {
        if (ys.every(y => document.elementFromPoint(x, y) === cv)) {
          run = run || { x0: x }; run.x1 = x;
          if (!best || run.x1 - run.x0 > best.x1 - best.x0) best = { x0: run.x0, x1: run.x1 };
        } else run = null;
      }
      return best && { x: best.x0, y: y0, width: best.x1 - best.x0, height: rows };
    }, FOOT_ROWS);
    if (seg && seg.short) throw new Error(`the map canvas ends at ${seg.bottom} px, above the foot of the window (${seg.H} px)`);
    if (!seg || seg.width < 100) throw new Error("nothing at the foot of the map is clear enough to check that it is drawn");
    const png = await page.screenshot({ clip: { x: 0, y: 0, ...VIEW } });      // the whole picture, not a clip of the strip
    const flat = await page.evaluate(async ([b64, s]) => {
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const bmp = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
      const c = document.createElement("canvas"); c.width = bmp.width; c.height = bmp.height;
      const g = c.getContext("2d"); g.drawImage(bmp, 0, 0);
      const d = g.getImageData(s.x, s.y, s.width, s.height).data;
      let n = 0;
      for (let y = 0; y < s.height; y++) {
        const lo = [255, 255, 255], hi = [0, 0, 0];
        for (let i = y * s.width * 4; i < (y + 1) * s.width * 4; i += 4) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], d[i + k]); hi[k] = Math.max(hi[k], d[i + k]); }
        if (hi.every((h, k) => h - lo[k] <= 3)) n++;
      }
      return n;
    }, [png.toString("base64"), seg]);
    if (flat < FOOT_ROWS - 2) return png;
    last = `${flat} of ${FOOT_ROWS} rows flat at x ${seg.x}–${seg.x + seg.width}, y ${seg.y}`;
  }
  throw new Error(`the foot of the map is blank (${last}); the map was drawn by ${RENDERER || "an unknown renderer"}`
    + (/SwiftShader/i.test(RENDERER) ? ", software, not the GPU" : ""));
}
async function mapIdle(page, extra = 1200) {
  await page.evaluate(() => new Promise(res => { if (map.loaded() && !map.isMoving()) { map.once("idle", res); map.triggerRepaint(); } else map.once("idle", res); setTimeout(res, 15000); }));
  await sleep(extra);
}
// the map's layers that open a popup on a click (map/index.html, every map.on('click', <layer>))
const CLICKABLE = ["rail-alignment", "ws-boundary-ticks", "ws-boundary-labels", "zone-fill", "temp-haul-lines", "site-gates",
                   "evr-rail-line", "locations", "restriction-points", "restriction-lines", "inbound-lines", "outbound-lines",
                   "forecast-layer"];
// Click a feature of one layer where no other clickable layer is drawn, so exactly one popup opens.
// `pick` keeps only the feature with that name (null = any). Returns the popup's text.
async function clickFeature(page, layer, center, zoom, pick) {
  await page.evaluate(([c, z]) => map.jumpTo({ center: c, zoom: z }), [center, zoom]);
  await mapIdle(page);
  const pt = await page.evaluate(([lid, pk, clickable]) => {
    const r = map.getCanvas().getBoundingClientRect();
    const other = (f) => f.layer && f.layer.id !== lid && clickable.includes(f.layer.id);
    const feats = map.queryRenderedFeatures({ layers: [lid] }).filter(f => !pk || (f.properties && f.properties.name === pk));
    const pts = [];
    feats.forEach(f => {
      const g = f.geometry, cs = g.type === "Point" ? [g.coordinates] : g.type === "LineString" ? g.coordinates
        : g.type === "MultiLineString" ? [].concat(...g.coordinates) : [];
      for (let i = 0; i < cs.length; i += Math.max(1, Math.floor(cs.length / 40))) pts.push(cs[i]);
    });
    const W = r.width, H = r.height;
    const ok = pts.map(c => map.project(c)).filter(p => p.x > W * 0.25 && p.x < W * 0.8 && p.y > H * 0.35 && p.y < H * 0.85)
      .sort((a, b) => Math.hypot(a.x - W / 2, a.y - H * 0.6) - Math.hypot(b.x - W / 2, b.y - H * 0.6));
    const nudges = [[0, 0], [4, 0], [-4, 0], [0, 4], [0, -4], [5, 5], [-5, 5], [5, -5], [-5, -5], [8, 0], [-8, 0], [0, 8], [0, -8]];
    // the click itself is a point query, so the target must be under the exact pixel; anything else
    // clickable must be clear of a small box round it
    for (const p of ok) for (const [dx, dy] of nudges) {
      const x = Math.round(p.x + dx), y = Math.round(p.y + dy);
      if (!map.queryRenderedFeatures([x, y]).some(f => f.layer.id === lid)) continue;
      if (!map.queryRenderedFeatures([[x - 1, y - 1], [x + 1, y + 1]]).some(other)) return { x: r.left + x, y: r.top + y };
    }
    return null;
  }, [layer, pick || null, CLICKABLE]);
  if (!pt) throw new Error(`no point on the ${layer} layer here that only it covers`);
  const thrown = [];
  const onErr = (e) => thrown.push(first(e));
  page.on("pageerror", onErr);
  try {
    await page.mouse.click(pt.x, pt.y);
    await page.locator(".mapboxgl-popup").last().waitFor({ timeout: 6000 });
  } catch (e) {
    // the map's own click handler threw: say what it said, so the failure names the bug, not this script
    throw new Error(thrown.length ? `the map threw on the ${layer} click, so no popup opened: ${thrown[0]}` : first(e));
  } finally {
    page.off("pageerror", onErr);
  }
  const pop = page.locator(".mapboxgl-popup").last();
  await sleep(1200);
  if (await page.locator(".mapboxgl-popup").count() > 1) throw new Error("more than one popup opened");
  return pop.innerText();
}
async function nodesOf(page, kind) {
  return page.evaluate((k) => (a1_data.features || []).filter(x => x.properties && x.properties.type === "Node"
    && (!k || String(x.properties.node_type || "").toLowerCase() === k.toLowerCase()))
    .map(f => ({ name: f.properties.name, ll: f.geometry.coordinates, kind: f.properties.node_type })), kind);
}
// the month on screen: this month if it carries approved volume, else the nearest month that does
async function pickMonth(page) {
  return page.evaluate(async () => {
    const n = CONFIG.MONTH_COUNT || 60, now = new Date();
    const here = Math.min(n, Math.max(1, (now.getFullYear() - CONFIG.START_YEAR) * 12 + now.getMonth() + 1));
    const j = await fetch(CONFIG.API_BASE + "/public/forecast-matrix?from=1&to=" + n + "&unit=" + (CONFIG.FORECAST_UNIT || "vehicles")).then(r => r.json());
    const vol = {};
    (j.routes || []).forEach(rt => Object.entries(rt.monthly || {}).forEach(([m, v]) => { vol[m] = (vol[m] || 0) + (+v || 0); }));
    const months = Object.keys(vol).filter(m => vol[m] > 0).map(Number);
    if (!months.length) return here;
    return months.sort((a, b) => Math.abs(a - here) - Math.abs(b - here) || a - b)[0];
  });
}

// ---- S15: the week PDF's first page -----------------------------------------------------
async function pdfFirstPage(context) {
  const r = await context.request.get(`${BASE}/api/forecast-weeks/export?format=pdf&bucket=commit`,
    { headers: { "X-Access-Code": CODE } });
  if (!r.ok()) throw new Error(`the PDF export answered ${r.status()}`);
  const bytes = await r.body();
  let png = null;
  try {  // poppler first, where installed
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "modus-guide-"));
    const pdf = path.join(tmp, "week.pdf");
    fs.writeFileSync(pdf, bytes);
    execFileSync("pdftoppm", ["-png", "-r", "110", "-f", "1", "-l", "1", pdf, path.join(tmp, "p")], { stdio: "ignore" });
    const f = fs.readdirSync(tmp).find(x => x.startsWith("p") && x.endsWith(".png"));
    if (f) png = "data:image/png;base64," + fs.readFileSync(path.join(tmp, f)).toString("base64");
  } catch (e) { png = null; }
  const pg = await context.newPage();
  try {
    await pg.setViewportSize(VIEW);
    if (!png) {
      // no poppler: pdf.js in this Chromium. The worker script runs on the main thread (pdf.js's
      // documented fallback when window.pdfjsWorker is loaded), so no cross-origin Worker is needed.
      await pg.setContent(`<!doctype html><html><head><script src="${PDFJS}"></script><script src="${PDFJS_WORKER}"></script></head><body></body></html>`,
        { waitUntil: "load" });
      png = await pg.evaluate(async ([b64, worker]) => {
        const lib = window.pdfjsLib;
        if (!lib) throw new Error("pdf.js did not load from cdnjs");
        lib.GlobalWorkerOptions.workerSrc = worker;
        const data = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const doc = await lib.getDocument({ data }).promise;
        const p1 = await doc.getPage(1);
        const vp = p1.getViewport({ scale: 1 });
        // 11 Oct 2026: drawn at the size it is shown (1380 px wide). Drawn at 1.5× and shrunk, thin strokes were
        // dropped (the minus of a longitude vanished).
        const scale = 1380 / vp.width;
        const v = p1.getViewport({ scale });
        const cv = document.createElement("canvas");
        cv.width = Math.ceil(v.width); cv.height = Math.ceil(v.height);
        const ctx = cv.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, cv.width, cv.height);
        await p1.render({ canvasContext: ctx, viewport: v }).promise;
        return cv.toDataURL("image/png");
      }, [Buffer.from(bytes).toString("base64"), PDFJS_WORKER]);
    }
    await pg.setContent(`<body style="margin:0;background:#E2E8F0;display:flex;justify-content:center">
      <img src="${png}" style="width:1380px;margin-top:20px;box-shadow:0 6px 24px rgba(15,23,42,.18)"></body>`, { waitUntil: "load" });
    await sleep(400);
    await pg.screenshot({ path: path.join(MEDIA, "S15.png"), clip: { x: 0, y: 0, ...VIEW } });
  } finally {
    await pg.close();
  }
}

(async () => {
  fs.mkdirSync(MEDIA, { recursive: true });
  let browser;
  try { browser = await chromium.launch({ args: [...GPU_ARGS, ...LANG_ARGS] }); }
  catch (e) {
    console.log(`  (Chromium would not start with the GPU arguments, so it starts without them; map shots may fail: ${first(e)})`);
    browser = await chromium.launch({ args: LANG_ARGS });
  }
  if (!ONLY.length) SKIP.forEach(id => skipped.push(`${id} (MODUS_SKIP${process.env.MODUS_SKIP === undefined ? ", the default" : ""}: its placeholder stays)`));
  const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 1, ...LOCALE });
  // the in-app tour's strip and dots off, in this throwaway browser only
  await context.addInitScript(() => {
    try { localStorage.setItem("wayscope_guide_all", "off"); localStorage.setItem("wayscope_guide_map", "off"); } catch (e) {}
  });
  // 🔴 the write guard: anything but a GET to the API is aborted, bar the three reads that take a body
  const ORIGIN = new URL(BASE).origin;
  await context.route((u) => u.origin === ORIGIN && u.pathname.startsWith("/api/"), (route) => {
    const req = route.request(), m = req.method();
    const p = new URL(req.url()).pathname;
    if (m === "GET" || m === "HEAD" || m === "OPTIONS" || READS_WITH_A_BODY.includes(p)) return route.continue();
    blocked.push(`${m} ${p}`);
    console.log("  ⛔ blocked", m, p);
    return route.abort();
  });
  const LIBS = process.env.MODUS_LOCAL_LIBS;
  if (LIBS) {
    const nm = (f) => fs.readFileSync(path.join(LIBS, "node_modules", f));
    const js = (body) => ({ status: 200, contentType: "application/javascript", body });
    const TW = fs.readFileSync(path.join(LIBS, "tw.css"), "utf8");
    const CDN = /^https:\/\/(unpkg\.com|cdn\.tailwindcss\.com|cdn\.jsdelivr\.net|api\.mapbox\.com\/mapbox-gl-js|fonts\.googleapis\.com|fonts\.gstatic\.com)\//;
    await context.route(CDN, (route) => {
      const u = route.request().url();
      if (u.includes("react-dom")) return route.fulfill(js(nm("react-dom/umd/react-dom.production.min.js")));
      if (u.includes("/react@")) return route.fulfill(js(nm("react/umd/react.production.min.js")));
      if (u.includes("babel")) return route.fulfill(js(nm("@babel/standalone/babel.min.js")));
      if (u.includes("chart")) return route.fulfill(js(nm("chart.js/dist/chart.umd.js")));
      if (u.includes("mapbox-gl.js")) return route.fulfill(js(nm("mapbox-gl/dist/mapbox-gl.js")));
      if (u.includes("mapbox-gl.css")) return route.fulfill({ status: 200, contentType: "text/css", body: nm("mapbox-gl/dist/mapbox-gl.css") });
      if (u.includes("tailwindcss")) {
        const inject = "(function(){var s=document.createElement(\"style\");s.textContent=" + JSON.stringify(TW)
          + ";(document.head||document.documentElement).appendChild(s);})();";
        return route.fulfill(js(inject));
      }
      return route.fulfill({ status: 200, contentType: "text/css", body: "" });   // fonts
    });
  }
  const page = await context.newPage();
  page.on("dialog", d => d.dismiss().catch(() => {}));   // never accept a confirm()

  console.log(`capturing from ${BASE} into ${MEDIA}`);
  // S01 — the sign-in screen, before anything is remembered
  await shot(page, "S01", async () => {
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await sleep(1200);
    const btn = page.getByText("Staff sign in").first();
    if (await btn.count() && !(await page.getByPlaceholder("Your name").count())) { await btn.click(); await sleep(800); }
    await page.getByPlaceholder("Your name").waitFor({ timeout: 10000 });
  });

  // sign in (sets the staff cookie that also opens /map/ and /help/)
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  const btn = page.getByText("Staff sign in").first();
  if (await btn.count() && !(await page.getByPlaceholder("Your name").count())) { await btn.click(); await sleep(600); }
  await page.getByPlaceholder("Your name").fill(WHO);
  await page.getByPlaceholder("Access code").fill(CODE);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByText("Sign out", { exact: true }).first().waitFor({ timeout: 20000 })
    .catch(() => { throw new Error("sign-in did not take: check MODUS_PLANNER_CODE"); });
  await sleep(2000);

  // S02 — the Dashboard: the six cards, the carbon-target strip, the charts
  await shot(page, "S02", async () => { await goApp(page, "dashboard", "Dashboard"); await sleep(1500); });
  // S03 — the folded Stockpile capacity section, opened
  await shot(page, "S03", async () => {
    await goApp(page, "dashboard", "Dashboard");
    const sum = page.locator("details.dash-more > summary", { hasText: /^Stockpile capacity$/ }).first();
    await sum.scrollIntoViewIfNeeded({ timeout: 10000 });
    if (!(await sum.evaluate(s => s.parentElement.open))) await sum.click();
    await page.waitForLoadState("networkidle").catch(() => {});
    await sleep(2500);
    await scrollUnderHeader(page, sum, 16);
    await sleep(1000);
  });
  // S04 — Submit forecast with an existing approved line loaded (the biggest); nothing typed, never saved
  await shot(page, "S04", async () => {
    await goApp(page, "submit", "Submit forecast");
    const H = { headers: { "X-Access-Code": CODE } };
    const rows = await (await context.request.get(`${BASE}/api/forecasts`, H)).json();
    const meta = await (await context.request.get(`${BASE}/api/meta`, H)).json();
    const tot = {};
    (rows || []).filter(r => r.status === "Approved").forEach(r => {
      const k = [r.route_id, r.discipline || "", r.section_id || ""].join("|");
      tot[k] = (tot[k] || 0) + (+r.quantity || 0);
    });
    const best = Object.entries(tot).sort((a, b) => b[1] - a[1])[0];
    if (best) {
      const [rid, disc, sec] = best[0].split("|");
      const rt = (meta.routes || []).find(r => r.route_id === rid);
      const sel = (label) => page.locator("label", { has: page.locator("span", { hasText: new RegExp("^" + label) }) }).locator("select").first();
      if (rt) {
        await sel("Origin").selectOption({ label: rt.origin });
        await sleep(500);
        await sel("Destination").selectOption({ label: rt.dest });
        await sleep(500);
        const ref = sel("Route reference");
        if (await ref.count()) await ref.selectOption(rid).catch(() => {});
        if (disc) await sel("Discipline").selectOption(disc).catch(() => {});
        if (sec) await sel("Work section").selectOption(sec).catch(() => {});
        await page.waitForLoadState("networkidle").catch(() => {});
        await sleep(2500);
      }
    }
    await scrollUnderHeader(page, page.getByText("From year", { exact: true }).first(), 20);
    await sleep(1500);
  });
  // S05 — Forecasts, as the planner. 11 Oct 2026: beside the open rail the table's Status column was cut off at 1440 px,
  // so the rail is folded for this picture (the app's own "‹ Collapse", in this throwaway browser) and opened again
  // after it, whatever happened. The shot fails unless the Status column's words, in its head and in every row on
  // screen, end inside the table's box (the column itself is wider than its words and runs on under the edge).
  await shot(page, "S05", async () => {
    await goApp(page, "forecasts", "Forecasts");
    await setRail(page, false);
    const st = page.locator("thead th", { hasText: /^Status$/ }).first();
    await st.waitFor({ timeout: 15000 });
    const fit = await st.evaluate((el) => {
      const head = el.parentElement, col = [...head.cells].indexOf(el), t = el.closest("table");
      let box = el.parentElement;
      while (box && !(box.scrollWidth > box.clientWidth + 4 && /auto|scroll/.test(getComputedStyle(box).overflowX))) box = box.parentElement;
      const bb = box ? box.getBoundingClientRect() : { right: window.innerWidth, bottom: window.innerHeight };
      const edge = Math.min(window.innerWidth, bb.right), foot = Math.min(window.innerHeight, bb.bottom);
      const cells = [el, ...[...t.tBodies[0].rows].filter(r => r.cells.length === head.cells.length).map(r => r.cells[col])];
      let right = 0, n = 0;
      for (const c of cells) {
        const cr = c.getBoundingClientRect();
        if (cr.top >= foot || cr.bottom <= 0) continue;
        const w = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
        for (let x = w.nextNode(); x; x = w.nextNode()) {
          if (!x.textContent.trim()) continue;
          const rg = document.createRange(); rg.selectNodeContents(x);
          for (const q of rg.getClientRects()) { right = Math.max(right, q.right); n++; }
        }
      }
      return { ok: n > 1 && right <= edge + 1, right: Math.round(right), edge: Math.round(edge) };
    });
    if (!fit.ok) throw new Error(`the Status column is cut off (its words end at ${fit.right} px, the table's box at ${fit.edge} px)`);
  });
  try { await setRail(page, true); }
  catch (e) { console.error("the rail would not open again after S05:", first(e)); }
  // S06 — Commit · this week: KPI strip, flags and the Monday–Friday grid
  await shot(page, "S06", () => lookahead(page, "commit"));
  // S07 — the last row expanded (▶ only; a day cell is never clicked) and the map under the grid
  await shot(page, "S07", async () => {
    await lookahead(page, "commit");
    const rows = page.locator("td.la-stick button[title^='Show ']");
    const n = await rows.count();
    if (!n) throw new Error("no line on the Commit grid");
    await rows.nth(n - 1).click({ timeout: 8000 });
    await sleep(1200);
    const target = page.locator("td.la-stick button").nth(Math.max(0, n - 2));
    await scrollUnderHeader(page, target, 40);
    await page.waitForLoadState("networkidle").catch(() => {});
    await sleep(3500);       // the week's map draws from its own fetch
  });
  // S08 — Account (last week) · S09 — Horizon. 11 Oct 2026: S08 shows the top of the lines table; the Stockpiles block
  // lies ~1,700 px under it (18 lines on the demo), so the caption no longer promises it (it said "and the Stockpiles block")
  await shot(page, "S08", () => lookahead(page, "Account"));
  await shot(page, "S09", () => lookahead(page, "Horizon"));
  // S10 — the Confirm week dialog, opened and CANCELLED
  await shot(page, "S10", async () => {
    await lookahead(page, "commit");
    let open = page.locator(HEADER_CONFIRM).first();
    if (!(await open.count()) || await open.isDisabled()) {
      // this week is confirmed already (or empty): next week, whose days are created when it opens
      await lookahead(page, "commit", "next week");
      open = page.locator(HEADER_CONFIRM).first();
      await page.waitForFunction((s) => { const b = document.querySelector(s); return b && !b.disabled; }, HEADER_CONFIRM, { timeout: 30000 });
    }
    await open.click({ timeout: 8000 });
    await confirmDialog(page).getByRole("button", { name: "Cancel", exact: true }).waitFor({ timeout: 8000 });
    await sleep(900);
  });
  // close the dialog without confirming, whatever the shot did — and stop if it will not close
  try { await cancelConfirmDialog(page); }
  catch (e) { console.error("🔴 the Confirm week dialog would not close: stopping here.", first(e)); await browser.close(); process.exit(1); }

  // S11 — Locations: a stockpile in the form, scrolled to its stock held and gates
  await shot(page, "S11", async () => {
    await dataPage(page, "locations", "Locations", "Stockpile Tilton", "Stockpile");
    await showGridTop(page);
    await scrollPanelTo(page, "Stock held");
  });
  // S12 — Routes: R001 selected (red on the map) and expanded. The list scrolls in its own box (40 % of the
  // window) inside the page: both are scrolled to the analysis table, the vehicle × primary/alternative rows.
  // 11 Oct 2026: aimed with scrollUnderHeader (the page used to be left where the shots before had scrolled it), and
  // the shot fails unless the table's head and first row are inside the picture and inside the list's box.
  await shot(page, "S12", async () => {
    await dataPage(page, "routes", "Routes", "R001");
    const row = page.locator("tbody tr", { hasText: "R001" }).first();
    await row.getByRole("button", { name: "Show analysis" }).click({ timeout: 8000 });
    await page.waitForLoadState("networkidle").catch(() => {});
    const th = page.locator("th", { hasText: /^Option$/ }).first();
    await th.waitFor({ timeout: 20000 });
    await sleep(1500);
    await scrollUnderHeader(page, th, 150);
    const at = await th.evaluate((el, [top, H]) => {
      const t = el.closest("table"), head = t.tHead.getBoundingClientRect(), r1 = t.tBodies[0] && t.tBodies[0].rows[0];
      let box = t.parentElement;
      while (box && !(box.scrollHeight > box.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
      const b = box ? box.getBoundingClientRect() : { top: 0, bottom: H };
      const sticky = box && box.querySelector("thead.sticky");          // the list's own head stays over its top
      const lo = Math.max(top, b.top + (sticky ? sticky.getBoundingClientRect().height : 0)), hi = Math.min(H, b.bottom);
      const end = r1 ? r1.getBoundingClientRect().bottom : Infinity;
      return { ok: head.top >= lo - 1 && end <= hi + 1, head: Math.round(head.top), end: Math.round(end), lo: Math.round(lo), hi: Math.round(hi) };
    }, [TOP, VIEW.height]);
    if (!at.ok) throw new Error(`the analysis table is not inside the picture (its head at ${at.head} px and its first row ending at ${at.end} px; the picture shows ${at.lo}–${at.hi} px of it)`);
  });
  // S13 — Zones: the demo's haul road in the form
  await shot(page, "S13", async () => {
    await dataPage(page, "zones", "Zones", "Langton haul road", "Temporary haul road");
    await showGridTop(page);
    await scrollPanelTo(page, "Kind");
  });
  // S14 — Configuration › Vehicles (the default section). Save is never pressed.
  await shot(page, "S14", () => goApp(page, "config", "Configuration"));
  // S16 — the Carbon planner, top: step 1 and the start of step 2, under the demo bar
  await shot(page, "S16", async () => {
    await goApp(page, "carbon", "Carbon planner");
    await page.locator("#carbon-step-2").waitFor({ timeout: 20000 });
    await page.waitForLoadState("networkidle").catch(() => {});
    await sleep(2500);
    await toTop(page);
    await sleep(600);
  });
  // S17 — step 6, the scheme's carbon target (as saved; nothing is set or cleared)
  await shot(page, "S17", async () => {
    await goApp(page, "carbon", "Carbon planner");
    await page.waitForFunction(() => !/Loading the carbon target/.test((document.getElementById("carbon-step-6") || {}).innerText || "x"), null, { timeout: 20000 });
    await page.waitForLoadState("networkidle").catch(() => {});
    await sleep(1500);
    await scrollUnderHeader(page, page.locator("#carbon-step-6"), 16);
  });
  // S15 — the supplier PDF, page 1 (its own tab)
  if (want("S15")) {
    try { await pdfFirstPage(context); done.push("S15"); console.log("  ✓ S15"); }
    catch (e) { failed.push(`S15: ${first(e)}`); console.log("  ✗ S15 —", first(e)); }
  }

  // ---- the public map ------------------------------------------------------------------
  const openMap = async () => {
    await page.goto(`${BASE}/map/`, { waitUntil: "networkidle" });
    await mapReady(page);
  };
  const MONTH = (want("M01") || want("M06")) ? await (async () => { await openMap(); return pickMonth(page); })().catch(() => null) : null;
  // M01 — the Control Panel with a month on screen (From = To = this month, Show forecast routes)
  await shot(page, "M01", async () => {
    await openMap();
    if (MONTH) {
      await page.selectOption("#forecast-from", String(MONTH));
      await page.selectOption("#forecast-to", String(MONTH));
      await page.locator("#toggle-forecast").check();
      await page.waitForFunction(() => !/No month on screen/.test(document.getElementById("kpi-title").innerText), null, { timeout: 20000 });
    }
    await mapIdle(page, 2000);
  });
  // M02 — the alignment popup, on a stretch with nothing else drawn over it
  await shot(page, "M02", async () => {
    await openMap();
    const ll = await page.evaluate(() => {
      const fs = (window.chainage_global_data && window.chainage_global_data.features) || [];
      const f = fs.find(x => Math.round(parseFloat(String(x.properties.chain).replace(/,/g, ""))) === 8000) || fs[Math.floor(fs.length / 4)];
      return f && f.geometry.coordinates;
    });
    if (!ll) throw new Error("the tenant has no alignment");
    const txt = await clickFeature(page, "rail-alignment", ll, 12.5);
    if (!/[0-9]/.test(txt)) throw new Error("the popup shows no chainage: " + txt.slice(0, 60));
  });
  // M03 — a stockpile's gauge and its popup
  await shot(page, "M03", async () => {
    await openMap();
    const piles = await nodesOf(page, "Stockpile");
    if (!piles.length) throw new Error("no stockpile on the map");
    let err = null;
    for (const p of piles) for (const z of [13, 14.5]) {      // a stockpile clear of the haul lines ending at it
      try { await clickFeature(page, "locations", p.ll, z, p.name); return; } catch (e) { err = e; }
    }
    throw err;
  });
  // M05 — a planned closure (GB) or a restriction (EE) and its popup, nearest the corridor
  if (want("M05")) {
    const prov = await context.request.get(`${BASE}/api/restrictions/layers`).then(r => r.ok() ? r.json() : {}).catch(() => ({}));
    if (!prov.provider || !(prov.layers || []).length) skipped.push("M05 (no road-closure or restriction provider for this tenant's country)");
    else await shot(page, "M05", async () => {
      await openMap();
      const key = prov.layers[0].key;
      await page.locator("#restr-" + key).check({ timeout: 15000 });
      // 11 Oct 2026: on the local copy the map never draws them (a map bug, reported, not worked round here: the
      // closures arrive while the basemap is still loading, ensureRestrictionLayers() waits for a style.load that
      // has already fired, and every later style.load finds the style still loading). The picture is taken only
      // if the map draws the closures by itself.
      const drawn = await page.waitForFunction(() => RESTR.data && map.getLayer("restriction-points"), null, { timeout: 20000 })
        .then(() => true, () => false);
      if (!drawn) throw new Error("ticking the closures box drew nothing: the map never added its closure layers (map bug, see the comment here)");
      const near = await page.evaluate(() => {
        const a = [].concat(...(window.alignment_data.features || []).map(f => f.geometry.type === "LineString" ? f.geometry.coordinates
          : f.geometry.type === "MultiLineString" ? [].concat(...f.geometry.coordinates) : []));
        const c = a.length ? [a.reduce((s, p) => s + p[0], 0) / a.length, a.reduce((s, p) => s + p[1], 0) / a.length] : map.getCenter().toArray();
        const pts = (RESTR.data.features || []).map(f => {
          const g = f.geometry; const cs = g.type === "Point" ? [g.coordinates] : g.type === "LineString" ? g.coordinates
            : g.type === "MultiLineString" ? [].concat(...g.coordinates) : [];
          const m = cs[Math.floor(cs.length / 2)];
          return m && { m, d: Math.hypot((m[0] - c[0]) * Math.cos(c[1] * Math.PI / 180), m[1] - c[1]) };
        }).filter(Boolean).sort((p, q) => p.d - q.d);
        return pts.length ? pts[0].m : null;
      });
      if (!near) throw new Error("the provider returned nothing to draw");
      let txt = null;
      for (const lid of ["restriction-points", "restriction-lines"]) {
        txt = await clickFeature(page, lid, near, 12).catch(() => null);
        if (txt) break;
      }
      if (!txt) throw new Error("no closure could be clicked near the corridor");
    });
  }
  // M06 — the timeline on this month, the figures bar, What's moving and Conditions
  await shot(page, "M06", async () => {
    await openMap();
    await page.locator("#tl-open").click({ timeout: 8000 });
    await page.waitForFunction(() => TL.matrix, null, { timeout: 30000 });
    if (MONTH) await page.locator("#tl-range").fill(String(MONTH));      // as dragging the slider does
    // the figures bar names the month once its figures have arrived
    await page.waitForFunction(() => document.getElementById("kpi-title").innerText.startsWith(monthLabel(TL.month)), null, { timeout: 30000 });
    await sleep(2500);
    const pill = page.locator("#kpi-conditions.on");
    if (await pill.count() && !(await page.locator("#tl-warnings").isVisible())) { await pill.click(); await sleep(1200); }
    await mapIdle(page, 1500);
  });
  // M07 — the satellite basemap (the quick button at the bottom left)
  await shot(page, "M07", async () => {
    await openMap();
    await page.locator('button.widget-btn[title="Satellite"]').click({ timeout: 8000 });
    await page.waitForFunction(() => /satellite/.test(JSON.stringify((map.getStyle() || {}).sprite || "") + (map.getStyle().name || "")), null, { timeout: 20000 }).catch(() => {});
    await mapIdle(page, 4000);
  });
  // M08 — a site popup with its Street View picture: the first site Google has imagery for
  await shot(page, "M08", async () => {
    await openMap();
    const sites = [...await nodesOf(page, "Quarry"), ...await nodesOf(page, null)];
    let pick = null, why = "";
    for (const s of sites) {
      const m = await context.request.get(`${BASE}/api/streetview/meta?lat=${s.ll[1]}&lon=${s.ll[0]}`).then(r => r.json()).catch(() => ({}));
      if (m.available) { pick = s; break; }
      why = m.status || "unavailable";
      if (m.status === "NO_KEY") break;            // no key on the server: no site will have a picture
    }
    if (!pick) throw new Error(`no site with a Street View picture (${why === "NO_KEY" ? "GOOGLE_MAPS_API_KEY is not set on the server" : "Google has no imagery near any site: " + why})`);
    await clickFeature(page, "locations", pick.ll, 14, pick.name);
    await page.locator('.mapboxgl-popup img[alt^="Street View"]').waitFor({ timeout: 15000 });
    await page.waitForFunction(() => { const i = document.querySelector('.mapboxgl-popup img[alt^="Street View"]'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 15000 });
    await sleep(800);
  });

  await browser.close();
  console.log(`\ncaptured ${done.length}: ${done.join(", ") || "—"}`);
  if (skipped.length) console.log(`skipped: ${skipped.join("; ")}`);
  if (blocked.length) console.log(`🔴 writes the page attempted and this script BLOCKED: ${blocked.join("; ")}`);
  if (failed.length) { console.log(`FAILED (their pictures were not touched): \n  ${failed.join("\n  ")}`); process.exit(1); }
  if (blocked.length) process.exit(1);
})().catch(e => { console.error(e); process.exit(1); });
