/*
 * harness_clock.js — the JS harnesses' clock, shifted to one fixed day (D104 for the JS harnesses).
 *
 * 18 Oct 2026. The staff Dashboard opens on this month ± 6 (D114), worked out from the browser's clock. The
 * harnesses that mount it with the fixture lines (cost_lines.json: Sep–Nov 2026) therefore aged with the calendar:
 * run in April 2027 the window no longer held September, and from June 2027 none of the fixture months, so the
 * route-table and figure checks failed on correct code (found by the D114-fix review, simulated with a faked clock).
 * http_smoke and test_h1_uk already read a pinned date (portable.pin_today, D104); this does the same here.
 *
 * The clock is SHIFTED, not frozen: Date.now() and `new Date()` read the real time plus a fixed offset, so time
 * still passes (timers, durations, "updated hh:mm") and only the day is moved. Dates built from arguments are not
 * touched. HARNESS_TODAY=YYYY-MM-DD runs a harness on another day, which is how the fix was checked
 * (e.g. HARNESS_TODAY=2027-06-15 node backend/tests/dom_frontend.js).
 *
 * Apply it to BOTH realms: the harness's own (where the checks work out "this month") with pinNode(), and the
 * context the app's script runs in (jsdom's window / a vm sandbox) by running shiftSource() there before the app.
 */
const vm = require("vm");

const TODAY = process.env.HARNESS_TODAY || "2026-10-15";          // a Thursday: month 10 of the fixtures' 2026 horizon
if (!/^\d{4}-\d{2}-\d{2}$/.test(TODAY)) throw new Error(`HARNESS_TODAY must be YYYY-MM-DD, not ${TODAY}`);
const RealDate = Date;
const OFFSET_MS = new RealDate(TODAY + "T12:00:00Z").getTime() - RealDate.now();

// the source that replaces Date in whatever realm runs it (idempotent: a second run is a no-op)
function shiftSource(offsetMs = OFFSET_MS) {
  return `(() => {
    const R = globalThis.Date;
    if (R.__harnessShifted) return;
    class Date extends R {
      constructor(...a) { if (a.length) super(...a); else super(R.now() + ${offsetMs}); }
      static now() { return R.now() + ${offsetMs}; }
    }
    Object.defineProperty(Date, "__harnessShifted", { value: true });
    globalThis.Date = Date;
  })();`;
}

function pinNode() { vm.runInThisContext(shiftSource()); return TODAY; }

module.exports = { TODAY, OFFSET_MS, shiftSource, pinNode };
