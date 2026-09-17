/*
 * tools/capture_guide.js — the user guide's real screenshots, captured from a running
 * deployment. Modus G2, 16 Sep 2026.
 *
 *   1. Deploy, import demo/uk-corridor.package.json into an EMPTY tenant
 *      (POST /api/admin/tenant/import?token=…), and bake the network (Routes → Bake all).
 *   2. From a machine that can reach the deployment AND the CDNs (a normal laptop):
 *
 *        npm i -g playwright && npx playwright install chromium
 *        MODUS_URL=https://your-deployment.example \
 *        MODUS_PLANNER_CODE=… \
 *        NODE_PATH=$(npm root -g) node backend/tools/capture_guide.js
 *
 *   3. Commit the PNGs it wrote into frontend/help/media/.
 *
 * It signs in with the PLANNER code (the guide's screens are the planner's view), walks
 * every page the guide shows, and overwrites S01–S15 and M01–M08 (M04 does not exist).
 * Each shot is independent: a shot that fails is reported and its placeholder is left in
 * place, so a partial run never leaves the guide with a broken image.
 *
 * 🔴 It never confirms, approves, bakes or saves anything. The Confirm-week dialog is
 *    opened for its picture and closed with Cancel.
 *
 * M05 (a road restriction and its verdict) needs a tenant whose country has a connected
 * restriction provider — today only Estonia. On the UK demo it is skipped and its
 * placeholder stays; the guide says the section applies only where a provider exists.
 *
 * ⚠️ NOT RUN against a live deployment when it was written: the sandbox that wrote it
 *    cannot reach the CDNs or Mapbox. The staff-app half was run against a local server
 *    with the libraries served from disk (MODUS_LOCAL_LIBS, below); the map half needs
 *    Mapbox and was not. Expect to adjust a wait or two on first use.
 *
 * MODUS_LOCAL_LIBS=<dir>  (a test aid for machines without CDN access) serves React,
 *    ReactDOM, Babel, Chart.js and mapbox-gl from <dir>/node_modules and a prebuilt
 *    <dir>/tw.css in place of the Tailwind CDN. Map tiles still need Mapbox, so the M
 *    shots fail in that mode — which is the honest outcome.
 */
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { chromium } = require("playwright");

const BASE = (process.env.MODUS_URL || "").replace(/\/+$/, "");
const CODE = process.env.MODUS_PLANNER_CODE || "";
const WHO = process.env.MODUS_NAME || "Guide capture";
// MODUS_OUT writes somewhere else (a dry run that must not replace the committed images)
const MEDIA = process.env.MODUS_OUT || path.resolve(__dirname, "..", "..", "frontend", "help", "media");
const ONLY = (process.env.MODUS_ONLY || "").split(",").map(s => s.trim()).filter(Boolean);
if (!BASE || !CODE) {
  console.error("Set MODUS_URL and MODUS_PLANNER_CODE (see the header of this file).");
  process.exit(2);
}

const VIEW = { width: 1440, height: 760 };
const done = [], failed = [], skipped = [];
const want = (id) => !ONLY.length || ONLY.includes(id);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function shot(page, id, fn) {
  if (!want(id)) return;
  try {
    await fn();
    await page.screenshot({ path: path.join(MEDIA, id + ".png"), clip: { x: 0, y: 0, ...VIEW } });
    done.push(id);
    console.log("  ✓", id);
  } catch (e) {
    failed.push(`${id}: ${String(e.message || e).split("\n")[0]}`);
    console.log("  ✗", id, "—", String(e.message || e).split("\n")[0]);
  }
}

async function goApp(page, hash) {
  await page.goto(`${BASE}/#${hash}`, { waitUntil: "networkidle" });
  await sleep(1500);
}

async function clickText(page, text, opts = {}) {
  const loc = page.getByText(text, { exact: !!opts.exact }).first();
  await loc.scrollIntoViewIfNeeded({ timeout: 8000 });
  await loc.click({ timeout: 8000 });
  await sleep(opts.wait || 1200);
}

// ---- the public map helpers: evaluate against the page's own `map` ---------------------
async function mapReady(page) {
  await page.waitForFunction(() => typeof map !== "undefined" && map.loaded && map.loaded()
    && window.alignment_data && typeof a1_data !== "undefined", null, { timeout: 45000 });
  await sleep(2500);
}
async function clickLngLat(page, lngLat, zoom) {
  const pt = await page.evaluate(([ll, z]) => {
    if (z) map.jumpTo({ center: ll, zoom: z });
    const p = map.project(ll);
    const r = map.getCanvas().getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  }, [lngLat, zoom]);
  await sleep(1800);
  const again = await page.evaluate((ll) => {
    const p = map.project(ll); const r = map.getCanvas().getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y };
  }, lngLat);
  await page.mouse.click(again.x || pt.x, again.y || pt.y);
  await sleep(1500);
}
async function nodeOf(page, kind) {
  return page.evaluate((k) => {
    const f = (a1_data.features || []).find(x => x.properties && x.properties.type === "Node"
      && String(x.properties.node_type || "").toLowerCase() === k.toLowerCase());
    return f ? f.geometry.coordinates : null;
  }, kind);
}

async function pdfFirstPage(context, page) {
  // download the week PDF with the planner code, then render its first page
  const r = await context.request.get(`${BASE}/api/forecast-weeks/export?format=pdf`,
    { headers: { "X-Access-Code": CODE } });
  if (!r.ok()) throw new Error(`PDF export answered ${r.status()}`);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "modus-guide-"));
  const pdf = path.join(tmp, "week.pdf");
  fs.writeFileSync(pdf, await r.body());
  try {  // poppler, where installed
    execFileSync("pdftoppm", ["-png", "-r", "110", "-f", "1", "-l", "1", pdf, path.join(tmp, "p")]);
    const png = fs.readdirSync(tmp).find(f => f.startsWith("p") && f.endsWith(".png"));
    const data = fs.readFileSync(path.join(tmp, png)).toString("base64");
    await page.setViewportSize(VIEW);
    await page.setContent(`<body style="margin:0;background:#E2E8F0;display:flex;justify-content:center">
      <img src="data:image/png;base64,${data}" style="width:1380px;margin-top:20px;box-shadow:0 6px 24px rgba(15,23,42,.18)"></body>`);
    await sleep(500);
  } catch (e) {
    throw new Error("pdftoppm (poppler) is needed to picture the PDF: " + e.message);
  }
}

(async () => {
  fs.mkdirSync(MEDIA, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 1 });
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

  console.log(`capturing from ${BASE}`);
  // S01 — the sign-in screen, before anything is remembered
  await shot(page, "S01", async () => {
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await sleep(1200);
    const btn = page.getByText("Staff sign in").first();
    if (await btn.count()) { await btn.click(); await sleep(800); }
    await page.getByPlaceholder("Your name").waitFor({ timeout: 10000 });
  });

  // sign in (sets the staff cookie that also opens /map/ and /help/)
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  const btn = page.getByText("Staff sign in").first();
  if (await btn.count()) { await btn.click(); await sleep(600); }
  await page.getByPlaceholder("Your name").fill(WHO);
  await page.getByPlaceholder("Access code").fill(CODE);
  await page.getByRole("button", { name: "Sign in" }).click();
  await sleep(2500);

  await shot(page, "S02", () => goApp(page, "dashboard"));
  await shot(page, "S03", async () => {
    await goApp(page, "dashboard");
    const t = page.locator(".chart-title", { hasText: "Stockpile capacity" }).first();
    await t.scrollIntoViewIfNeeded({ timeout: 15000 });
    await page.evaluate(() => window.scrollBy(0, -80));
    await sleep(1500);
  });
  await shot(page, "S04", () => goApp(page, "submit"));
  await shot(page, "S05", () => goApp(page, "forecasts"));
  await shot(page, "S06", () => goApp(page, "lookahead"));
  await shot(page, "S07", async () => {
    await goApp(page, "lookahead");
    await page.locator("text=/^R0\\d\\d$/").first().click({ timeout: 8000 }).catch(() => {});
    await sleep(1500);
    await page.mouse.wheel(0, 420); await sleep(1200);
  });
  await shot(page, "S08", async () => { await goApp(page, "lookahead"); await clickText(page, "Account", { exact: true, wait: 2500 }); });
  await shot(page, "S09", async () => { await goApp(page, "lookahead"); await clickText(page, "Horizon", { exact: true, wait: 2500 }); });
  await shot(page, "S10", async () => {
    await goApp(page, "lookahead");
    await page.getByRole("button", { name: "next week", exact: true }).click({ timeout: 8000 });
    // next week's days are created on demand; wait until the button is live
    await page.waitForFunction(() => [...document.querySelectorAll("button")].some(b =>
      /^Confirm (week|remaining lines)$/.test(b.textContent.trim()) && !b.disabled), null, { timeout: 30000 });
    await page.getByRole("button", { name: /^Confirm (week|remaining lines)$/ }).first().click({ timeout: 8000 });
    await page.getByRole("button", { name: "Cancel" }).first().waitFor({ timeout: 8000 });
    await sleep(900);
  });
  // close the dialog without confirming, whatever the shot did
  await page.getByRole("button", { name: "Cancel" }).first().click({ timeout: 3000 }).catch(() => {});
  await shot(page, "S11", async () => { await goApp(page, "locations"); await clickText(page, "Stockpile Tilton", { wait: 2000 }).catch(() => {}); });
  await shot(page, "S12", async () => { await goApp(page, "routes"); await page.locator("text=/^R001$/").first().click({ timeout: 8000 }).catch(() => {}); await sleep(2000); });
  await shot(page, "S13", async () => { await goApp(page, "zones"); await clickText(page, "Langton haul road", { wait: 2000 }).catch(() => {}); });
  await shot(page, "S14", () => goApp(page, "config"));
  await shot(page, "S15", () => pdfFirstPage(context, page));

  // ---- the route map ----------------------------------------------------------------
  const openMap = async () => { await page.setViewportSize(VIEW); await page.goto(`${BASE}/map/`, { waitUntil: "networkidle" }); await mapReady(page); };
  await shot(page, "M01", openMap);
  await shot(page, "M02", async () => {
    await openMap();
    const ll = await page.evaluate(() => {
      const f = (window.chainage_global_data.features || []).find(x => Math.round(parseFloat(String(x.properties.chain).replace(/,/g, ""))) === 8000)
        || window.chainage_global_data.features[Math.floor(window.chainage_global_data.features.length / 4)];
      return f && f.geometry.coordinates;
    });
    if (!ll) throw new Error("the tenant has no alignment");
    await clickLngLat(page, ll, 12.5);
  });
  await shot(page, "M03", async () => {
    await openMap();
    const ll = await nodeOf(page, "Stockpile");
    if (!ll) throw new Error("no stockpile on the map");
    await clickLngLat(page, ll, 13);
  });
  if (want("M05")) {
    const hasProvider = await page.evaluate(() => typeof RESTR !== "undefined" && !!RESTR.provider).catch(() => false);
    if (!hasProvider) { skipped.push("M05 (no road-restriction provider for this tenant's country)"); }
    else await shot(page, "M05", async () => { await openMap(); await page.locator("#restrictions-group input[type=checkbox]").first().check(); await sleep(3000); });
  }
  await shot(page, "M06", async () => {
    await openMap();
    await page.evaluate(() => { if (typeof openTimeline === "function") openTimeline(); });
    await sleep(3500);
  });
  await shot(page, "M07", async () => {
    await openMap();
    await page.selectOption("#basemap-select", "mapbox://styles/mapbox/satellite-streets-v12");
    await sleep(6000);
  });
  await shot(page, "M08", async () => {
    await openMap();
    const ll = await nodeOf(page, "Quarry");
    if (!ll) throw new Error("no quarry on the map");
    await clickLngLat(page, ll, 14);
    await page.getByText("Street View").first().click({ timeout: 5000 }).catch(() => {});
    await sleep(3500);
  });

  await browser.close();
  console.log(`\ncaptured ${done.length}: ${done.join(", ") || "—"}`);
  if (skipped.length) console.log(`skipped: ${skipped.join("; ")}`);
  if (failed.length) { console.log(`FAILED (placeholders kept): \n  ${failed.join("\n  ")}`); process.exit(1); }
})().catch(e => { console.error(e); process.exit(1); });
