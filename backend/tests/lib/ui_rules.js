/*
 * lib/ui_rules.js — the UX programme's rules as measures (FR1, notes\ux-programme-1109.md §3, rows A1a, A1b, A1c, A3).
 * 10 Nov 2026, branch claude/audit-measures-rules. A helper, not a harness (run_suite runs every backend/tests/*.js, so a
 * helper lives in lib/). Used by ui_audit.js (in Google Chrome, every stop) and by ui_audit_rules.js (in CI, under jsdom).
 *
 *   A1a  screen words      visible words per stop, leaving out table cells, figures, chart labels and keys, form fields,
 *                          menus and the "i" boxes; --compare warns when a stop grows by more than 10 % or 25 words
 *   A1b  long prose        a visible block of more than 25 words outside an "i" box: a FAILURE on a staff screen, a
 *                          warning elsewhere; chart keys, the guides and the landing pages are skipped. Known blocks are
 *                          pinned (LONG_PROSE_PINNED), a warning, and the list may only shrink
 *   A1c  filled primaries  filled primary buttons visible on first view; a warning above one
 *   A3   page ready        navigation → the page's first figure, per stop; --compare warns when 25 % slower and over 1 s.
 *                          The laptop's local copy: it shows a page getting slower in the browser, never live's speed
 *
 * John's limits (decision U5, 10 Nov 2026, mockup Q6–Q9, "all as recommended"); starting points, tuned after the first
 * two runs (§3: "The first two runs set the baseline and John signs off the numbers").
 *
 * The page-side functions (ruleMeasures, pageReadyNow) run INSIDE the page (Playwright's page.evaluate / waitForFunction,
 * or a jsdom window): they must stay self-contained — no reference to anything outside their own body.
 */
"use strict";

const LIMITS = {
  blockWords: 25,       // A1b: more than this many words in one block fails (staff) / warns (elsewhere)
  proseShare: 0.6,      // ...a block is prose when at least this share of its tokens has a letter (not a row of figures)
  wordsGrowPct: 10,     // A1a: a stop that grows by MORE than this % ...
  wordsGrowAbs: 25,     // ...or by more than this many words warns
  primaries: 1,         // A1c: more than this many filled primaries on first view warns
  readySlowerPct: 25,   // A3: this much slower than the earlier run ...
  readyFloorMs: 1000,   // ...AND over this many ms warns
  readyCapMs: 20000,    // A3: a page with no figure after this long is recorded as null (ready-none)
};
// the version of the rule measures a report carries (REPORT.ruleVersion). An earlier run without it (0) has no word counts,
// no blocks, no primaries and no page-ready times: --compare reports this run's rule findings as FIRST MEASURED, never as new
// findings, and computes no word or speed change for a stop the earlier run did not measure.
const RULES_VERSION = 1;
// the finding ids these measures add; the compare-time ones are recomputed every compare and never keyed as findings
const RULE_IDS = ["long-prose", "long-prose-pinned", "filled-primaries", "ready-none"];
const COMPARE_IDS = ["words-grew", "ready-slower"];

// A1b's pinned list (U5 / Q10: the five long sentences on live today are removed by claude/ui-fix-long-sentences, which merges
// after the 13 Nov freeze). Exactly the blocks the first two runs of this branch found on staff screens: a pinned block is a
// warning (long-prose-pinned), any other block on a staff screen fails. The list may ONLY SHRINK (ui_audit_rules.js pins
// its length); a pin no run sees any more is named in the run's notes for removal. `starts` is the block's opening, matched
// on pinKey (lower case, figures as #, spaces collapsed). `where` is where the first run found it, for the reader.
const LONG_PROSE_PINNED = [
  // the first quick run, 10 Nov 2026 (ui-audit 2026-11-10_212940 on main 992c4d3): 26 blocks on staff screens. Five are the
  // sentences of U5 / Q10 that claude/ui-fix-long-sentences removes; the rest sit in folds, tabs and pages the 10 Nov live check
  // did not open (notes\session-1110-audit-measures-rules.md lists them, and the ones that are data, not copy)
  { starts: "All three use Government factors. GOV.UK says", where: "carbon+open (Carbon planner, a section opened), 71 words" },
  { starts: "Planned arrivals spread evenly over the gate's open hours", where: "lookahead (gates note), 50 words" },
  { starts: "Lorries for Tilton Compound and Tilton Viaduct site", where: "simulation, simulation+site, team-simulation, 390 and 1366 (holding-area sentence, built from the data), 42 words" },
  { starts: "The waste hierarchy step follows the disposal method", where: "carbon+open, 40 words" },
  { starts: "This route already carries", where: "submit (Q10's sentence, 38 words; 18 since PR #257 moved the advice into an i box, kept while its list of lines can pass 25)" },
  { starts: "Battery electric is worked out as kWh per km", where: "carbon+open, 38 words" },
  { starts: "Injury collisions reported to the police, five years", where: "config-map-and-bulletin, 38 words" },
  { starts: "£/trip = fuel + cycle hours", where: "config-costing-fuel, 34 words" },
  { starts: "These figures are for your team's lines only", where: "team-carbon, 33 words" },
  { starts: "The agreed decisions: Receiving site", where: "dashboard+open, dashboard+row (a CLP note built from the data), 32 words" },
  { starts: "One page: the approved plan beside the alternative", where: "carbon+open, 32 words" },
  { starts: "Optional. Puts a value on the lorry-days", where: "config-costing-fuel, 32 words" },
  { starts: "Schools, hospitals, stations, bus stops, homes", where: "config-map-and-bulletin, 31 words" },
  { starts: "They get an email with a link to choose their password", where: "login-user-users, 31 words" },
  { starts: "Per load has no target line", where: "dashboard+open, dashboard+row (CLP note), 30 words" },
  { starts: "Writes the decisions it commits to into the construction logistics plan", where: "carbon+open, 30 words" },
  { starts: "DESNZ 2026, WTT- delivery vehs & freight", where: "carbon+open (a factor's source path), 28 words" },
  { starts: "Site plant and site energy, staff travel", where: "carbon+open, 27 words" },
  { starts: "UK Government GHG conversion factors 2026 (DESNZ). The National Highways", where: "carbon+open, 27 words" },
  { starts: "A lorry's working day. Its trips fit one driver's day", where: "config-planning, 27 words" },
  { starts: "Artic Flatbed (44t) — electric: payload", where: "carbon+open (a vehicle's figures in a line), 26 words" },
  { starts: "Artic Tipper (44t) — electric: payload", where: "carbon+open (a vehicle's figures in a line), 26 words" },
];

// the stops A1b and A1a's growth warning skip: the two guides (where explanation belongs) and the landing pages (marketing
// prose, its own page). The bulletin and the public map are graded, as a warning (not staff screens).
const PROSE_SKIPPED = /^(help|help-technical|landing|privacy|thanks|landing-error)$/;
// a staff screen: signed in to the app (the rail or the phone's tab bar is on the page), and not the client reviewer's page
const isStaffStop = (stop) => !!stop.signedIn && !/^review-/.test(stop.name);
const pinKey = (s) => String(s || "").toLowerCase().replace(/\d+([.,:]\d+)*/g, "#").replace(/\s+/g, " ").trim();
const pinOf = (text, pins) => (pins || LONG_PROSE_PINNED).find(p => pinKey(text).startsWith(pinKey(p.starts)));

// ---------------------------------------------------------------- inside the page ----------------------------------
// A1a, A1b and A1c for the page as it stands. Returns { scope, words, skipped: {…}, blocks: [...], primaries: [...] }.
function ruleMeasures(arg) {
  arg = arg || {};
  const LIMIT = arg.blockWords || 25, SHARE = arg.proseShare || 0.6;
  // what is not counted as screen words: tables, form fields, menus (the rail, the phone's tabs, a nav, a row menu),
  // chart labels and keys (SVG and canvas text, the app's and the map's keys), the "i" boxes (the button and the panel),
  // the map's credits, and what nobody sees (scripts, aria-hidden, a screen-reader-only box)
  const SKIP = {
    table: 'table, [role="table"], [role="grid"], [role="treegrid"]',
    form: 'input, select, textarea, option, [contenteditable="true"]',
    menu: 'nav, [role="menu"], [role="menubar"], [role="listbox"], [data-guide="rail"], .phone-tabs, details.row-menu',
    chart: 'svg, canvas, [class*="legend"], .sim-key, .lp-key, .ga-key, .cm-key, .tl-keys, .ml-key, .mapboxgl-ctrl-attrib, .mapboxgl-ctrl-logo',
    info: '.info-pop, .ibtn, [data-info-box]',
    unseen: 'script, style, noscript, template, [aria-hidden="true"]',
  };
  const skipAll = Object.values(SKIP).join(", ");
  const visCache = new Map();
  const vis = (el) => {
    if (visCache.has(el)) return visCache.get(el);
    let v = true;
    if (el.closest("[hidden], details:not([open]) > :not(summary)")) v = false;
    else if (typeof el.checkVisibility === "function") v = el.checkVisibility({ opacityProperty: true, visibilityProperty: true });
    else { for (let e = el; e && e !== document.documentElement; e = e.parentElement) { const cs = getComputedStyle(e); if (cs.display === "none" || cs.visibility === "hidden" || (cs.opacity !== "" && +cs.opacity === 0)) { v = false; break; } } }
    if (v) { const r = el.getBoundingClientRect(); if (!r.width && !r.height) v = false;
      // a screen-reader-only box (.sr-only: 1 px, clipped) is not on screen
      const cs = getComputedStyle(el); if (cs.position === "absolute" && parseFloat(cs.width) <= 1 && parseFloat(cs.height) <= 1) v = false; }
    visCache.set(el, v); return v;
  };
  const sel = (el) => { let s = el.tagName.toLowerCase(); if (el.id) s += "#" + el.id; else if (el.className && typeof el.className === "string" && el.className.trim()) s += "." + el.className.trim().split(/\s+/).slice(0, 2).join("."); return s; };
  const hasLetter = (t) => /[A-Za-zÀ-ɏ]/.test(t);
  // the portal scrolls inside its own <main class="… overflow-auto">: the page is that; anything else, the whole body
  const scroller = document.querySelector("main.overflow-auto");
  const root = scroller || document.body;
  const out = { scope: scroller ? "main" : "body", words: 0, skipped: {}, blocks: [], primaries: [] };
  for (const k of Object.keys(SKIP)) out.skipped[k] = 0;
  out.skipped.figures = 0;
  // the block a text node belongs to: its nearest ancestor that is not inline (a flex or grid item is blockified)
  const blockOf = (el) => { for (let e = el; e && e !== root.parentElement; e = e.parentElement) { const d = getComputedStyle(e).display || "";
    if (d && !d.startsWith("inline") && d !== "contents") return e; } return root; };
  // the text of each block, its text nodes joined as drawn: React splits "line" + "s" into two ADJACENT text nodes, which read
  // as one word, so a node that directly follows the last one joins it with nothing; anything between them (a <br>, a skipped
  // "i" button, another element) gives a space, so words are never merged
  const allB = new Map(), proseB = new Map();
  const add = (m, b, node, raw) => { const r = m.get(b); if (!r) m.set(b, { text: raw, last: node }); else { r.text += (node.previousSibling === r.last ? "" : " ") + raw; r.last = node; } };
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    const raw = n.textContent.replace(/\s+/g, " "); if (!raw.trim()) continue;
    const el = n.parentElement; if (!el) continue;
    if (el.closest(skipAll)) { if (!vis(el) && !el.closest(SKIP.info)) continue;
      const kind = Object.keys(SKIP).find(k => el.closest(SKIP[k])); out.skipped[kind] += raw.trim().split(" ").filter(hasLetter).length; continue; }
    if (!vis(el)) continue;
    const b = blockOf(el);
    add(allB, b, n, raw);
    // A1b: a control's label is not prose (a button, a tab); a link inside a sentence is
    if (!el.closest('button, [role="button"], [role="tab"]')) add(proseB, b, n, raw);
  }
  for (const r of allB.values()) { const toks = r.text.trim().split(" ").filter(Boolean); const w = toks.filter(hasLetter).length; out.words += w; out.skipped.figures += toks.length - w; }
  for (const [b, r] of proseB) {
    const text = r.text.replace(/\s+/g, " ").trim(), toks = text.split(" ").filter(Boolean);
    const lettered = toks.filter(hasLetter).length;
    if (toks.length > LIMIT && lettered >= SHARE * toks.length) out.blocks.push({ words: toks.length, sel: sel(b), text: text.slice(0, 160) });
  }
  // A1c: filled primaries on FIRST VIEW (inside the viewport as the stop opens, not under a sheet). The app's and the map's
  // primary is the accent: an inline background of var(--action) (the rule since PR #246; Dark keeps the attribute) or a
  // computed background equal to --action (.btn-pri, the map's .btn). A selected segment or tab is selection, not an action.
  // A page with no --action (the guides, the bulletin, the landing page): a control filled with a strong colour and light text.
  const probe = document.createElement("div"); probe.style.background = "var(--action)"; probe.style.position = "absolute"; (document.body || document.documentElement).appendChild(probe);
  const actionBg = getComputedStyle(probe).backgroundColor; probe.remove();
  const rgb = (s) => { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(s || ""); return m ? [+m[1], +m[2], +m[3], m[4] == null ? 1 : +m[4]] : null; };
  const actionRgb = rgb(actionBg);
  const hasAction = (actionRgb && actionRgb[3] > 0.9) || !!document.querySelector('[style*="var(--action)"]');
  const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const same = (a, b) => !!a && !!b && Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) <= 6;
  const inView = (el) => { const r = el.getBoundingClientRect(); if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) return false;
    const x = Math.min(Math.max((r.left + r.right) / 2, 0), innerWidth - 1), y = Math.min(Math.max((r.top + r.bottom) / 2, 0), innerHeight - 1);
    const h = typeof document.elementFromPoint === "function" ? document.elementFromPoint(x, y) : null;
    return !h || h === el || el.contains(h) || h.contains(el); };
  // first view = the top of the page: a scroller left part-way down by an earlier stop (the keyboard pass Tabs through it)
  // goes to the top for the count, and back after
  const st = scroller ? scroller.scrollTop : 0, wy = window.scrollY || 0;
  try { if (scroller) scroller.scrollTop = 0; if (wy) window.scrollTo(0, 0); } catch (e) {}
  for (const el of document.querySelectorAll('button, a[href], [role="button"], input[type="submit"], input[type="button"]')) {
    if (!vis(el) || el.closest(".demo-bar, " + SKIP.menu + ", " + SKIP.info) || !inView(el)) continue;
    if (el.getAttribute("aria-pressed") === "true" || el.getAttribute("aria-selected") === "true" || el.hasAttribute("aria-current") || el.getAttribute("role") === "tab") continue;
    const cs = getComputedStyle(el); const bg = rgb(cs.backgroundColor);
    let how = null;
    if (hasAction) {
      if (/background[^;]*var\(--action\)/.test(el.getAttribute("style") || "")) how = "action";
      else if (bg && bg[3] > 0.9 && same(bg, actionRgb)) how = "action";
    } else if (bg && bg[3] > 0.9) {
      const mx = Math.max(bg[0], bg[1], bg[2]), mn = Math.min(bg[0], bg[1], bg[2]); const fg = rgb(cs.color);
      const r = el.getBoundingClientRect();
      if (mx >= 60 && (mx - mn) / mx >= 0.3 && fg && ratio(fg, bg) >= 3 && r.width >= 40 && r.height >= 20) how = "filled";
    }
    if (how) out.primaries.push({ sel: sel(el), text: (el.getAttribute("aria-label") || el.textContent || el.value || "").replace(/\s+/g, " ").trim().slice(0, 60), how });
  }
  try { if (scroller) scroller.scrollTop = st; if (wy) window.scrollTo(0, wy); } catch (e) {}
  return out;
}

// A3: has the page shown its first figure? Inside the page, polled from the navigation on. arg: { title, map }.
// The page header must be the page asked for (a phone's desk-only card counts); then ready = a visible figure (a digit in the
// page's text outside its header, chart labels included, or a number in a field), the page's own empty / error state, or the
// desk-only card. Other parts of the page may still say "Loading…": the FIRST figure is what a reader waits for. The map
// page: the map loaded and a figure outside the map's canvas.
function pageReadyNow(arg) {
  arg = arg || {};
  const shown = (el) => { const r = el.getBoundingClientRect(); return !!(r.width || r.height) && !el.closest("[hidden], details:not([open]) > :not(summary)"); };
  if (arg.map) { try { if (typeof map === "undefined" || !map || !map.loaded()) return false; } catch (e) { return false; } }
  const desk = document.querySelector("[data-desk-only]"); if (desk && shown(desk)) return true;
  if (arg.title) { const h = document.querySelector('[data-guide="page-header"] h2'); if (!h || h.textContent.trim() !== arg.title) return false; }
  const root = document.querySelector("main.overflow-auto") || document.body;
  const empty = root.querySelector("[data-empty]"); if (empty && shown(empty)) return true;
  const outside = '[data-guide="page-header"], [data-guide="rail"], .phone-tabs, .demo-bar, nav, script, style, .mapboxgl-map';
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { if (!/\d/.test(n.textContent)) continue; const el = n.parentElement; if (el && !el.closest(outside) && shown(el)) return true; }
  for (const f of root.querySelectorAll("input")) if (/\d/.test(f.value || "") && !f.closest(outside) && shown(f)) return true;
  return false;
}

// ---------------------------------------------------------------- in Node: grading one stop ------------------------
// stop: the stop's record (name, page, signedIn); m: ruleMeasures' answer. Returns the checks and warnings to add, and the
// pins this stop matched (so a run can name a pin nothing matches any more).
function gradeRules(stop, m, pins) {
  const checks = [], warnings = [], pinsSeen = [];
  if (!m) return { checks, warnings, pinsSeen };
  if (!PROSE_SKIPPED.test(stop.name)) {
    const pinned = [], open = [];
    for (const b of m.blocks || []) { const p = pinOf(b.text, pins); if (p) { pinned.push({ ...b, pin: p.starts }); pinsSeen.push(p.starts); } else open.push(b); }
    if (isStaffStop(stop)) checks.push({ id: "long-prose", ok: open.length === 0, detail: open });
    else if (open.length) warnings.push({ id: "long-prose", detail: open });
    if (pinned.length) warnings.push({ id: "long-prose-pinned", detail: pinned });
  }
  if ((m.primaries || []).length > LIMITS.primaries) warnings.push({ id: "filled-primaries", detail: m.primaries });
  return { checks, warnings, pinsSeen };
}

// ---------------------------------------------------------------- in Node: comparing two runs ----------------------
const stopKey = (s) => `${s.name}|${s.width}|${s.look}|${s.accent}`;
// prev, now: the two reports. Returns { words: [...], ready: [...], unsettled: [...], earlierMeasured } — a row per stop both
// runs measured; `warn` set on the rows that cross the limits. A stop the earlier run did not measure (an older run: no
// `words`) gets no row. A stop that had not finished loading in EITHER run (a not-settled or ready-none warning) gets no row
// either, only its key in `unsettled`: on 10 Nov 2026 the Look-ahead at 390 read 238 words settled and 12 unsettled, and the
// team's Look-ahead 23 → 222 the other way round — the machine's load, not the page
const UNSETTLED = ["not-settled", "ready-none"];
const unsettledStop = (s) => (s.warnings || []).some(w => UNSETTLED.includes(w.id));
function compareRules(prev, now) {
  const earlierMeasured = (prev.ruleVersion || 0) >= 1;
  const byKey = new Map((prev.stops || []).map(s => [stopKey(s), s]));
  const words = [], ready = [], unsettled = [];
  for (const s of now.stops || []) {
    const p = byKey.get(stopKey(s)); if (!p) continue;
    if (unsettledStop(s) || unsettledStop(p)) { if (s.words != null || s.readyMs != null) unsettled.push(stopKey(s)); continue; }
    if (s.words != null && p.words != null && s.words !== p.words) {
      const delta = s.words - p.words, pct = p.words ? Math.round(delta * 1000 / p.words) / 10 : (delta > 0 ? Infinity : 0);
      const warn = !PROSE_SKIPPED.test(s.name) && (delta > LIMITS.wordsGrowAbs || pct > LIMITS.wordsGrowPct);
      words.push({ key: stopKey(s), name: s.name, was: p.words, now: s.words, delta, pct, warn });
    }
    if (s.readyMs != null && p.readyMs != null) {
      const warn = s.readyMs > LIMITS.readyFloorMs && s.readyMs >= p.readyMs * (1 + LIMITS.readySlowerPct / 100);
      ready.push({ key: stopKey(s), name: s.name, was: p.readyMs, now: s.readyMs, warn });
    }
  }
  return { words, ready, unsettled, earlierMeasured };
}
// a compare's new finding keys (name|width|look|accent|id|…) split: those of a rule check the earlier run did not have are
// FIRST MEASURED, not new; the compare-time ids are never findings
function splitFindings(keys, earlierMeasured) {
  const idOf = (k) => k.split("|")[4];
  const fresh = [], first = [];
  for (const k of keys) { const id = idOf(k); if (COMPARE_IDS.includes(id)) continue; (!earlierMeasured && RULE_IDS.includes(id) ? first : fresh).push(k); }
  return { fresh, first };
}

// ---------------------------------------------------------------- in Node: the PR lines ------------------------------
// The three lines a UI PR carries (notes\ux-programme-1109.md §2, L1 step 3): new failing checks, screen words +/− per stop
// touched, the slowest page-ready time. report: the run's report (with .compare when it compared).
function prLines(report) {
  const L = [];
  const c = report.compare;
  const failIds = new Set();
  for (const s of report.stops || []) for (const ch of s.checks || []) if (!ch.ok) failIds.add(stopKey(s) + "|" + ch.id);
  if (c) {
    const newFail = (c.newFindings || []).filter(k => failIds.has(k.split("|").slice(0, 5).join("|")));
    L.push(`- **New failing checks:** ${newFail.length}${newFail.length ? " — " + [...new Set(newFail.map(k => k.split("|").slice(0, 5).join(" ")))].slice(0, 12).join("; ") : ""}`);
    if (c.firstMeasured && c.firstMeasured.length) L.push(`  (${c.firstMeasured.length} finding(s) of the rule checks are FIRST MEASURED: the earlier run had no rule measures, so they are not counted as new)`);
    const w = (c.rules && c.rules.words) || [];
    if (!c.rules || !c.rules.earlierMeasured) L.push("- **Screen words +/−:** the earlier run has no word counts (made before the rule measures); the next compare has them");
    else if (!w.length) L.push("- **Screen words +/−:** no stop changed");
    else { L.push(`- **Screen words +/−** (${w.length} stop(s) changed${w.some(r => r.warn) ? ", " + w.filter(r => r.warn).length + " over the limit" : ""}):`);
      for (const r of w.slice().sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 25)) L.push(`  - ${r.key.replace(/\|/g, " ")}: ${r.was} → ${r.now} (${r.delta > 0 ? "+" : ""}${r.delta}${isFinite(r.pct) ? ", " + (r.pct > 0 ? "+" : "") + r.pct + " %" : ""})${r.warn ? " ⚠" : ""}`); }
  } else L.push("- **New failing checks / screen words +/−:** no compare in this run (pass --compare latest)");
  const timed = (report.stops || []).filter(s => s.readyMs != null).sort((a, b) => b.readyMs - a.readyMs);
  if (timed.length) { const s = timed[0]; L.push(`- **Slowest page ready:** ${s.readyMs} ms, ${s.name} at ${s.width} px (${s.look}) — the laptop's local copy, not live's speed`); }
  if (c && c.rules && c.rules.earlierMeasured && (c.rules.unsettled || []).length) L.push(`  (${c.rules.unsettled.length} stop(s) not compared: the page had not finished loading in one of the two runs — ${c.rules.unsettled.slice(0, 6).map(k => k.replace(/\|/g, " ")).join("; ")})`);
  const slower = c && c.rules ? c.rules.ready.filter(r => r.warn) : [];
  if (slower.length) L.push(`  ${slower.length} stop(s) 25 % slower and over 1 s: ${slower.slice(0, 8).map(r => r.key.replace(/\|/g, " ") + " " + r.was + " → " + r.now + " ms").join("; ")}`);
  return L;
}

// ---------------------------------------------------------------- fixtures: a bad page and a good one ---------------
// The same pages are measured in Google Chrome (ui_audit.js, at the start of every run, and --self-test) and under jsdom
// (ui_audit_rules.js, in CI). `expect` is what ruleMeasures must answer. data-fixture-top is read only by the jsdom layout
// stub (jsdom draws nothing); in Chrome the margin puts the element below the fold.
const LONG = "This sentence explains far too much on a staff screen because it walks through every step of the working, names each input in turn and then repeats the result again for good measure.";   // 33 words
const FIXTURES = {
  bad: {
    html: `<!doctype html><html><head><style>:root{--action:#C2410C}.btn-pri{background:var(--action);color:#fff;padding:6px 12px;border:0}
      .sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}</style></head><body>
      <main class="flex-1 overflow-auto" style="height:600px">
        <div data-guide="page-header"><h2>Bad page</h2></div>
        <p id="long">${LONG}</p>
        <button type="button" style="background: var(--action); color:#fff">Save plan</button>
        <button type="button" class="btn-pri">Send now</button>
        <button type="button" aria-pressed="true" class="btn-pri">Selected</button>
        <table><tr><td>${LONG}</td></tr></table>
        <svg width="200" height="40"><text x="0" y="20">${LONG}</text></svg>
        <div class="ga-key">${LONG}</div>
        <div class="info-pop" role="dialog"><p>${LONG}</p></div>
        <input value="${LONG}">
        <details><summary>More</summary><p>${LONG}</p></details>
        <p hidden>${LONG}</p>
        <span class="sr-only">${LONG}</span>
        <p>Delivered 63 of 120 loads</p>
        <div style="margin-top:3000px" data-fixture-top="3000"><button type="button" class="btn-pri">Far below</button></div>
      </main></body></html>`,
    // 33 (the long sentence) + 2 + 2 (two buttons) + 1 ("Selected") + 2 ("Bad page") + 1 ("More") + 3 ("Delivered of loads") + 2 ("Far below")
    expect: { words: 46, blocks: 1, blockWords: 33, primaries: 2 },
  },
  good: {
    html: `<!doctype html><html><head><style>:root{--action:#C2410C}.btn-pri{background:var(--action);color:#fff;padding:6px 12px;border:0}</style></head><body>
      <main class="flex-1 overflow-auto" style="height:600px">
        <div data-guide="page-header"><h2>Good page</h2></div>
        <p>Busiest hour · 63 loads a day <button type="button" class="ibtn" aria-label="About: Busiest hour">i</button></p>
        <p>Short status. All lines approved.</p>
        <button type="button" class="btn-pri">Approve week</button>
        <button type="button" class="btn-sec">Download</button>
        <table><tr><td>${LONG}</td></tr></table>
        <p id="split"></p>
        <script>var s = document.getElementById("split"); s.appendChild(document.createTextNode("2 other forecast line")); s.appendChild(document.createTextNode("s"));</script>
      </main></body></html>`,
    // "Good page" 2 + "Busiest hour loads a day" 5 (the "i" is the box's, "·" and "63" are figures) + 5 + "Approve week" 2 + "Download" 1
    // + "other forecast lines" 3 (React's two text nodes "line" + "s" in one element read as ONE word, as drawn)
    expect: { words: 18, blocks: 0, primaries: 1 },
  },
  // A3: "Loading…" first, the figure 400 ms later (a script); ready must wait for it
  slow: {
    html: `<!doctype html><html><body><main class="overflow-auto"><div data-guide="page-header"><h2>Slow page</h2></div>
      <div id="box"><span>Loading…</span></div>
      <script>setTimeout(function(){ document.getElementById("box").innerHTML = "<span>405 loads this week</span>"; }, 400);</script></main></body></html>`,
    expect: { readyAfterMs: 350 },
  },
};

module.exports = { LIMITS, RULES_VERSION, RULE_IDS, COMPARE_IDS, LONG_PROSE_PINNED, PROSE_SKIPPED, isStaffStop, pinKey, pinOf,
  ruleMeasures, pageReadyNow, gradeRules, stopKey, compareRules, splitFindings, prLines, FIXTURES };
