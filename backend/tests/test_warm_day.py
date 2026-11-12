"""
The read cache's warmer also runs when the day turns over, 11 Nov 2026 (CLOCS meeting card B-F8).

On live on 11 Nov the Zones page took 6.1 s and 4.1 s to show its diversions the first time, then 0.13-0.23 s. The
diversions read is on the warm-up list (main._warm_staff), but the staff reads are keyed by the day (main._staff_json:
a week or "this month" turns at midnight) and the warmer only ran again when the data version moved. With no write
since the evening before, every warmed staff read (Dashboard, Look-ahead, Routes, Zones) was cold for the first person
each morning. read_cache.due() now also says yes when the day has changed.

What is asserted:
  * due(): after start-up; never twice for the same version and day; a moved version waits for WARM_QUIET_S of quiet
    (as before); the same version on a new day warms at once (new); a moved version on a new day still waits for the
    quiet (a re-import over midnight is not warmed half way);
  * the warmer thread calls due() with today's date, and remembers the day it warmed;
  * the diversions read is still on the staff warm-up list, as the admin calls it (route_id=None).

WHAT THIS DOES NOT PROVE: the thread's timing on live (Render runs one process; the first open after midnight is
measured by hand after the merge). Nothing here starts the thread.

Run:  python backend/tests/test_warm_day.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

import read_cache  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(f"{label} {extra}".strip())
        print("  FAIL", label, extra)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


Q = read_cache.WARM_QUIET_S
due = getattr(read_cache, "due", None)
ok("due() exists", callable(due))
if callable(due):
    ok("after start-up: warm", due(None, None, 7, "2026-11-11", 0.0) is True)
    ok("the same version, the same day: nothing to do", due(7, "2026-11-11", 7, "2026-11-11", 9999.0) is False)
    ok("a moved version, writes still landing: wait", due(7, "2026-11-11", 8, "2026-11-11", Q - 1) is False)
    ok("a moved version, quiet for WARM_QUIET_S: warm", due(7, "2026-11-11", 8, "2026-11-11", Q) is True)
    ok("NEW: the same version on a new day: warm at once (the staff reads are keyed by the day)",
       due(7, "2026-11-11", 7, "2026-11-12", 0.0) is True)
    ok("a moved version on a new day still waits for the quiet (a re-import over midnight)",
       due(7, "2026-11-11", 8, "2026-11-12", Q - 1) is False and due(7, "2026-11-11", 8, "2026-11-12", Q) is True)

SRC = read("backend/read_cache.py")
_w = SRC.split("def start_warmer(")[1]
ok("the thread asks due() with today's date and remembers the day it warmed",
   "datetime.date.today().isoformat()" in _w and "if due(warmed_at, warmed_day, v, day," in _w
   and "warmed_at, warmed_day = v, day" in _w)
ok("WARM_QUIET_S and WARM_TICK_S unchanged", read_cache.WARM_QUIET_S == 30.0 and read_cache.WARM_TICK_S == 10.0)
MAIN = read("backend/main.py")
_ws = MAIN.split("def _warm_staff():")[1].split("\nread_cache.WARMERS")[0]
ok("the Zones page's diversions read is on the staff warm-up list, as the page asks for it",
   "routes_diversions(route_id=None)" in _ws and 'read_cache.WARMERS["staff"] = _warm_staff' in MAIN)
ok("the staff reads are still keyed by the day (why the turnover matters)",
   re.search(r"def _staff_json\(.*?_dt\.date\.today\(\)\.isoformat\(\)", MAIN, re.S) is not None)

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
