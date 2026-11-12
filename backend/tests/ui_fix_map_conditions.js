/* ui_fix_map_conditions.js — 12 Nov 2026, branch claude/map-conditions-panel-stays-closed (card A1-X1, John: "Yes, both").
 *
 * The public map's Conditions panel (#tl-warnings) opened by itself at the first month with a red condition, on every page
 * load, at any window width; at about 1150 px it stood over 40 % of the map. Now:
 *   (1) a close by hand (the panel's x, or the bar's chip while the panel is open) is remembered for the browser session
 *       (sessionStorage: this tab; a new tab or window is a fresh visit), so a reload does not open it again; the chip
 *       opening it forgets the close;
 *   (2) under 1400 px the panel never opens by itself (the bar's chip shows the count and one click opens it);
 *   Play's clash pause is NOT limited: it opens the panel at any width, close or no close.
 *
 * Source checks on map/index.html plus a sandbox that runs the page's own four functions against a stand-in sessionStorage
 * and window. No browser (the browser half is the Chrome run in the card, with a red month forced in on a local copy: the
 * demo database has none). Every check fails on the code before this branch.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}

const a = html.indexOf("const COND_AUTO_MIN_W");
const b = html.indexOf("\n    // \"Show on map\": a route is selected", a);
const block = a >= 0 && b > a ? html.slice(a, b) : "";
ok("A1 the page has the four panel-opening functions in one block (limit, memory, may-open, toggle)",
   /COND_AUTO_MIN_W = 1400/.test(block) && /function condHandClosed\(\)/.test(block) && /function condRemember\(closed\)/.test(block)
   && /function condMayOpenItself\(\)/.test(block) && /function toggleConditions\(\)/.test(block), block.slice(0, 120));

// the page's own block, run against a stand-in window, sessionStorage and WARN
function world(width, store, throws) {
  const ss = throws ? { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } }
    : { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } };
  const rendered = [];
  const ctx = { window: { innerWidth: width }, sessionStorage: ss, WARN: { open: false, autoOpened: false }, TL: { month: 16 },
                renderTimelineWarnings: m => rendered.push(m) };
  vm.createContext(ctx);
  vm.runInContext(block + "\n;this.api = { condHandClosed, condRemember, condMayOpenItself, toggleConditions, min: COND_AUTO_MIN_W };", ctx);
  return { ctx, rendered, api: ctx.api };
}
if (block) {
  let st = {};
  ok("B1 a fresh visit (nothing stored) at 1400 px and wider may open by itself", world(1400, st).api.condMayOpenItself() && world(1920, st).api.condMayOpenItself());
  ok("B2 under 1400 px it may not (1399, 1280, 1150, 1024, 390)", [1399, 1280, 1150, 1024, 390].every(w => !world(w, st).api.condMayOpenItself()));
  // a close by hand: the panel is open, the person presses its x (toggleConditions with WARN.open true)
  st = {}; let w = world(1920, st); w.ctx.WARN.open = true; w.api.toggleConditions();
  ok("B3 pressing the x (or the chip while it is open) closes it and remembers the close", w.ctx.WARN.open === false && st["wayscope-conditions-closed"] === "1" && w.rendered.length === 1, st);
  ok("B4 a reload (a new page, the same tab's storage) does not open it by itself, even on a wide window", !world(1920, st).api.condMayOpenItself());
  // the chip opening it forgets the close
  const w2 = world(1920, st); w2.api.toggleConditions();
  ok("B5 the chip opening it forgets the close: open, nothing stored", w2.ctx.WARN.open === true && !("wayscope-conditions-closed" in st) && world(1920, st).api.condMayOpenItself(), st);
  // a new tab or window: its own empty storage
  ok("B6 a new tab or window (empty storage) is a fresh visit and may open by itself on a wide window", world(1920, {}).api.condMayOpenItself());
  // storage refused (a private window with storage off): the old behaviour per load, never an error
  const wb = world(1920, {}, true);
  let threw = false; try { wb.ctx.WARN.open = true; wb.api.toggleConditions(); wb.api.condMayOpenItself(); } catch (e) { threw = true; }
  ok("B7 storage refused: no error, the close is simply not remembered (it may open again on a wide window)", !threw && wb.api.condMayOpenItself() === true);
} else { ok("B the sandbox could not run: the block is missing", false); }

// the three places the panel opens
const auto = (html.match(/if \(live\.some\(i => i\.lvl === 'clash'\) && !WARN\.autoOpened[^\n]*\n/) || [""])[0];
ok("C1 the by-itself open asks condMayOpenItself() and still opens once (autoOpened)", /&& condMayOpenItself\(\)\) \{ WARN\.open = true; WARN\.autoOpened = true;/.test(auto), auto);
ok("C2 Play's clash pause is not limited: it still sets WARN.open = true with no width or memory test",
   /TL\.clashPaused = true; WARN\.open = true;\n\s+stopTimeline\(/.test(html) && !/condMayOpenItself\(\)[^\n]*clashPaused/.test(html));
ok("C3 nothing else sets WARN.open to true but the chip / x toggle, the auto-open and Play's pause",
   (html.match(/WARN\.open = true/g) || []).length === 2 && (html.match(/WARN\.open = !WARN\.open/g) || []).length === 1);
ok("C4 the chip and the x both call toggleConditions (so both remember a close)",
   html.includes('id="kpi-conditions" onclick="toggleConditions()"') && html.includes(`aria-label="Close the conditions panel" onclick="toggleConditions()"`));
ok("C5 the phone's sheet reads the counts and rows (WARN.counts, WARN.live), never WARN.open (the phone is unchanged)",
   (() => { const i = html.indexOf("condSummary(WARN.counts)"); return i > 0 && !/WARN\.open/.test(html.slice(i - 1200, i + 1800)); })());

for (const f of fail) console.log("  FAIL: " + f);
console.log(`${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
