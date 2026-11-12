/* ui_fix_map_timeline_keep.js — 11 Nov 2026, branch claude/map-timeline-keep (on claude/map-first-view, PR #256, merged with
 * main): card A-F6 on John's "Yes, as recommended" (notes\clocs-meeting-1113\left-to-do-mockup-1111\cards-live-a-public.html).
 *
 *   1. The timeline bar's × and Esc close the BAR and keep the month on screen with its figures (they cleared it: "—"
 *      everywhere and "No month on screen" in the middle of a demo). Picking the month on screen again in the Control
 *      Panel, with the bar closed, clears it (the old × result, still reachable); a month or Play brings the bar back.
 *   2. "Pause on clash" starts unticked for a visitor; a tick BY HAND is remembered in that browser (a new key, as the
 *      old one was written on every opening of the bar and cannot tell a tick from the old default).
 *
 * Source checks plus sandboxes of the map's own functions; no browser. Every check of a change fails on the code before
 * this branch.
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const html = fs.readFileSync(path.join(ROOT, "map", "index.html"), "utf8").replace(/\r\n?/g, "\n");
const guide = fs.readFileSync(path.join(ROOT, "frontend", "help", "index.html"), "utf8").replace(/\r\n?/g, "\n");

let pass = 0; const fail = [];
function ok(label, cond, extra) {
  if (cond) { pass++; console.log("  ✓ " + label); }
  else { fail.push(label + (extra !== undefined ? "  → " + JSON.stringify(extra).slice(0, 400) : "")); console.log("  ✗ " + label); }
}
function fnSrc(name) {
  let i = html.indexOf("    function " + name + "(");
  if (i < 0) return "";
  const j = html.indexOf("\n    function ", i + 10);
  return html.slice(i, j > 0 ? j : i + 6000);
}

console.log("1. the × and Esc keep the month");
{
  const bar = html.slice(html.indexOf('<div id="timeline-bar"'), html.indexOf('<div id="timeline-bar"') + 9000);
  ok("⭐ the bar's × calls hideTimelineBar (closeTimeline cleared the month)",
     html.includes('<button type="button" class="tl-close" onclick="hideTimelineBar()" title="Close timeline" aria-label="Close the timeline">&times;</button>')
     && !/class="tl-close" onclick="closeTimeline\(\)"/.test(html));
  ok("⭐ Esc in the bar does the same", html.includes("else if(e.key === 'Escape' && inBar && !TL.wall){ e.preventDefault(); hideTimelineBar(); }")
     && !html.includes("inBar && !TL.wall){ e.preventDefault(); closeTimeline(); }"));
  // the four functions in one sandbox with a fake page
  const src = ["timelineBarShown", "showTimelineBar", "hideTimelineBar", "pickMonth"].map(fnSrc).join("\n");
  const log = [];
  const barEl = { style: { display: "flex" } };
  const ctx = {
    TL: { on: true, month: 16, chosen: true, playing: true, wall: false, clashPaused: true }, CONFIG: { MONTH_COUNT: 60 },
    document: { getElementById: id => (id === "timeline-bar" ? barEl : null) },
    stopTimeline: () => { log.push("stop"); ctx.TL.playing = false; }, hideClashToast: () => log.push("toast-off"),
    syncTimelineFoot: () => log.push("foot"), exitWallMode: () => log.push("wall-off"),
    closeTimeline: () => { log.push("clear"); ctx.TL.on = false; barEl.style.display = "none"; },
    openTimeline: () => { log.push("open"); ctx.TL.on = true; barEl.style.display = "flex"; },
    setTimelineMonth: m => { log.push("month " + m); ctx.TL.month = m; },
  };
  vm.createContext(ctx);
  let err = "";
  try { vm.runInContext(src + "\nthis.F = { timelineBarShown, showTimelineBar, hideTimelineBar, pickMonth };", ctx); } catch (x) { err = String(x); }
  const F = ctx.F;
  ok("the bar's functions run in a sandbox", !!F && typeof F.hideTimelineBar === "function", err);
  if (F) {
    F.hideTimelineBar();
    ok("⭐ the × stops Play, hides the bar and its pause message, and KEEPS the month on screen (TL.on, TL.month)",
       barEl.style.display === "none" && ctx.TL.on === true && ctx.TL.month === 16 && !ctx.TL.playing && log.includes("toast-off") && !log.includes("clear"), log);
    log.length = 0;
    F.pickMonth(18);
    ok("⭐ another month picked in the Control Panel shows it and brings the bar back", ctx.TL.month === 18 && barEl.style.display === "flex" && !log.includes("clear"), log);
    F.hideTimelineBar(); log.length = 0;
    F.pickMonth(18);
    ok("⭐ the month on screen picked again with the bar closed clears it (the old × result)", log.includes("clear") && ctx.TL.on === false, log);
    ctx.TL.on = true; barEl.style.display = "flex"; log.length = 0;
    F.pickMonth(18);
    ok("...but with the bar open, picking the month on screen does NOT clear it (a visitor pressing 'Apr' to see April)",
       !log.includes("clear") && ctx.TL.on === true && log.includes("month 18"), log);
    ctx.TL.wall = true; log.length = 0;
    F.hideTimelineBar();
    ok("closing the bar from wall mode leaves wall mode first", log[0] === "wall-off");
    ctx.TL.wall = false;
  }
  ok("⭐ Play brings a closed bar back with the month (startTimeline)",
     /function startTimeline\(\)\{[\s\S]{0,200}if\(TL\.on && typeof showTimelineBar === 'function'\) showTimelineBar\(\);[^\n]*\n\s*if\(!TL\.on\) openTimeline\(\);/.test(html));
  ok("closeTimeline still clears (a 'month=none' link and the re-pick use it)", /function closeTimeline\(\)\{[\s\S]{0,200}TL\.cleared = true;/.test(html));
  ok("the guide says the × keeps the month and how to see every route with no month",
     guide.includes("The timeline bar's × closes the bar and keeps the month on screen; to see every route with no month, close the bar and press the month on screen again")
     && guide.includes("× closes the bar (the month stays)") && !guide.includes("Close the timeline bar (×) to see every route with no month"));
}

console.log("2. Pause on clash starts unticked");
{
  const head = html.slice(html.indexOf("    TL.pauseOnClash = "), html.indexOf("    function setTimelineFull("));
  const run = store => {
    const ctx = { TL: {}, localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
                  document: { getElementById: () => ({ checked: null }) } };
    vm.createContext(ctx);
    vm.runInContext(head + "\n" + fnSrc("setPauseOnClash") + "\nthis.set = setPauseOnClash;", ctx);
    return ctx;
  };
  let a = null, err = "";
  try { a = run({}); } catch (x) { err = String(x); }
  ok("the switch's start runs in a sandbox", !!a, err);
  if (a) {
    ok("⭐ a new visitor: Pause on clash is OFF", a.TL.pauseOnClash === false);
    const st = {}; const b = run(st);
    b.set(b.TL.pauseOnClash);   // the bar opening syncs the switch: writes nothing
    ok("⭐ opening the bar writes nothing (the old code stored the default on every opening)", Object.keys(st).length === 0, st);
    b.set(true, true);
    ok("⭐ a tick by hand is remembered: the next visit starts ticked", st.modus_tl_pause_hand === "1" && run(st).TL.pauseOnClash === true, st);
    b.set(false, true);
    ok("an untick by hand is remembered too", st.modus_tl_pause_hand === "0" && run(st).TL.pauseOnClash === false);
    ok("⭐ the old key (written on every opening) is not read: an old '1' starts unticked", run({ modus_tl_pause: "1" }).TL.pauseOnClash === false);
  }
  ok("⭐ the switch is drawn unticked and its change is a choice by hand",
     html.includes('<input type="checkbox" id="tl-pause-clash" role="switch" onchange="setPauseOnClash(this.checked, true)">'));
  ok("'Stop pausing on clashes' is a choice by hand", html.includes("function stopPausingOnClash(){ setPauseOnClash(false, true); startTimeline(); }"));
  ok("the guide says it is off unless ticked, and remembered", guide.includes("<strong>Pause on clash</strong>, off unless you tick it, stops Play once a loop on the first month that is over capacity; this browser remembers your choice."));
}

console.log();
fail.forEach(f => console.log("  FAIL: " + f));
console.log(`\n${pass} passed, ${fail.length} failed`);
process.exit(fail.length ? 1 : 0);
