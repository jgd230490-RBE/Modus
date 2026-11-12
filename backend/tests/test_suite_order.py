"""
test_suite_order.py — the suite runs the Python harnesses that WRITE a fixture before the JS harnesses that READ it.
12 Nov 2026 (claude/suite-fixture-order).

Why: run_suite.py ran every JS harness first, so in CI render_frontend.js and dom_frontend.js rendered the fixtures
committed on 27 Oct and never the shape the backend sends now (test_lookahead.py's own comment said "the js harness
runs after this file"; it did not). run_suite now runs run_suite.FIXTURE_WRITERS first. This file holds that:
  1. every FIXTURE_WRITERS harness exists, names its fixtures and opens each for writing;
  2. in run_suite.harnesses() every writer comes before every JS harness;
  3. every fixture a default-suite JS harness reads is written by a FIXTURE_WRITERS harness, or is named in
     COMMITTED_ONLY below (a hand-made fixture no harness writes), so a NEW fixture cannot be read before it is written;
  4. every test_*.py that writes one of those fixtures is in FIXTURE_WRITERS.
No backend import, no database: it reads sources and calls harnesses() with stand-in interpreters.
"""
import glob
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_suite  # noqa: E402  (its main() runs only as __main__)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label + (f"  {extra}" if extra else ""))


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def writes_fixture(src, fx):
    """True when src opens the fixture fx for writing: inline, open(os.path.join(..., "fx"), "w"), or through a
    variable set to a path ending in it and later opened with "w". Naming it alone (test_modus names one) is not."""
    q = re.escape(fx)
    if re.search(r'open\([^\n]*"' + q + r'"[^\n]*"w"', src):
        return True
    for var in re.findall(r'(\w+)\s*=\s*os\.path\.join\([^\n]*"' + q + r'"\)', src):
        if re.search(r'open\(' + re.escape(var) + r',\s*"w"', src):
            return True
    return False


# fixtures a JS harness reads that no harness writes (hand-made, committed only); empty on 12 Nov 2026
COMMITTED_ONLY = set()

WRITERS = getattr(run_suite, "FIXTURE_WRITERS", None)
ok("run_suite.py names its fixture writers (FIXTURE_WRITERS: harness -> the fixtures it writes)",
   isinstance(WRITERS, dict) and len(WRITERS) >= 8, str(type(WRITERS)))
WRITERS = WRITERS if isinstance(WRITERS, dict) else {}
written = {fx for fxs in WRITERS.values() for fx in fxs}

# 1. each writer exists, names its fixtures and writes each one
for h, fxs in sorted(WRITERS.items()):
    p = os.path.join(HERE, h)
    src = read(p) if os.path.exists(p) else ""
    ok(f"{h} exists and opens {', '.join(fxs)} for writing",
       bool(src) and all(writes_fixture(src, fx) for fx in fxs))

# 2. the order harnesses() gives
def listed(only=None):
    return run_suite.harnesses(types.SimpleNamespace(py="PY", node="NODE", smoke_py="SMOKE", only=only))


full = listed()
order = [os.path.basename(f) for f, _ in full]
js_at = [i for i, n in enumerate(order) if n.endswith(".js")]
wr_at = {n: i for i, n in enumerate(order) if n in WRITERS}
ok("every FIXTURE_WRITERS harness is in the suite", set(wr_at) == set(WRITERS), str(set(WRITERS) - set(wr_at)))
ok("⭐ every fixture writer runs BEFORE the first JS harness (so the JS harnesses render what the backend sends now)",
   bool(js_at) and bool(wr_at) and max(wr_at.values()) < min(js_at),
   f"last writer at {max(wr_at.values(), default=None)}, first JS at {min(js_at, default=None)}")
ok("the writers run with --py, the JS harnesses with --node, every other test_*.py after the JS",
   all(cmd[0] == "PY" for f, cmd in full if os.path.basename(f) in WRITERS)
   and all(cmd[0] == "NODE" for f, cmd in full if f.endswith(".js"))
   and all(i > max(js_at) for i, n in enumerate(order) if n.startswith("test_") and n.endswith(".py") and n not in WRITERS))
ok("nothing is run twice or dropped: every test_*.py and default-suite *.js appears once",
   len(order) == len(set(order))
   and {os.path.basename(f) for f in glob.glob(os.path.join(HERE, "test_*.py"))} <= set(order)
   and {os.path.basename(f) for f in glob.glob(os.path.join(HERE, "*.js"))} - run_suite.BROWSER_ONLY <= set(order))
ok("http_smoke.py and the smoke_*.py still come last, with --smoke-py",
   order[-1].startswith("smoke_") and all(cmd[0] == "SMOKE" for f, cmd in full
                                          if os.path.basename(f) == "http_smoke.py" or os.path.basename(f).startswith("smoke_")))
ok("--only still narrows the list, writer first",
   [os.path.basename(f) for f, _ in listed(["render_frontend", "test_lookahead"])] == ["test_lookahead.py", "render_frontend.js"])

# 3. what the default-suite JS harnesses read
READ_PAT = re.compile(r'"fixtures",\s*"([a-z0-9_]+\.json)"|\bFIX\("([a-z0-9_]+\.json)"\)')
reads = {}
for f in sorted(glob.glob(os.path.join(HERE, "*.js"))):
    n = os.path.basename(f)
    if n in run_suite.BROWSER_ONLY:
        continue
    for m in READ_PAT.finditer(read(f)):
        reads.setdefault(m.group(1) or m.group(2), set()).add(n)
ok("the JS harnesses' fixture reads are found (render_frontend.js and dom_frontend.js read lookahead_page.json)",
   {"render_frontend.js", "dom_frontend.js"} <= reads.get("lookahead_page.json", set()), str(reads.get("lookahead_page.json")))
unwritten = {fx: sorted(by) for fx, by in reads.items() if fx not in written and fx not in COMMITTED_ONLY}
ok("⭐ every fixture a JS harness reads is written by a FIXTURE_WRITERS harness (or is named COMMITTED_ONLY here)",
   not unwritten, str(unwritten))

# 4. every Python harness that writes one of those fixtures is listed (test_modus only names cost_lines.json: not one)
found = {}
for f in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    n = os.path.basename(f)
    if n == os.path.basename(__file__):
        continue
    writes = sorted(fx for fx in reads if writes_fixture(read(f), fx))
    if writes:
        found[n] = writes
        ok(f"{n} writes {', '.join(writes)}, which a JS harness reads, so it is in FIXTURE_WRITERS with them",
           n in WRITERS and set(writes) <= set(WRITERS[n]), str(WRITERS.get(n)))
ok("the writer search finds exactly the harnesses run_suite names", set(found) == set(WRITERS),
   str(sorted(set(found) ^ set(WRITERS))))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
