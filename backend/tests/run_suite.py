"""
run_suite.py — every harness in the default suite, one count table at the end.  14 Oct 2026 (HU7).

Written for CI (.github/workflows/suite.yml) and just as usable on the laptop:

    $env:PYTHONUTF8 = "1"; $env:NODE_PATH = (npm root -g)
    .venv-tests\\Scripts\\python backend/tests/run_suite.py --smoke-py .venv-smoke\\Scripts\\python.exe

What it runs, in this order (the order CLAUDE.md "Tests" gives):
  1. every backend/tests/*.js except BROWSER_ONLY (each of those says in its header that it needs a
     real browser and is not part of the default suite) — with --node;
  2. every backend/tests/test_*.py — with --py, the interpreter WITHOUT FastAPI (the harnesses stub it);
  3. backend/tests/http_smoke.py — with --smoke-py, the interpreter with backend/requirements.txt.
A new harness that follows the naming is picked up without editing this file.

A harness FAILS when any of these is true — so a harness that quietly did nothing cannot pass:
  - its exit code is not 0;
  - its output has no "N passed, M failed" line (the last such line is the count);
  - M > 0, or N == 0;
  - it printed "SKIPPED" (dom_frontend.js without jsdom, http_smoke.py without FastAPI both exit 0).

Offline: every child gets PYTHONUTF8=1 and NONE of the external keys below, so no harness can spend a
HERE or Mapbox call or send mail. --require-offline (CI) also checks first that api.mapbox.com and
router.hereapi.com cannot be reached at all, and stops if they can — in CI the run sits in a network
namespace with no route out, so a harness that needs the network fails there instead of passing on luck.

Fixtures: test_costlines.py, test_lookahead.py (and others) rewrite files in backend/tests/fixtures/.
The table's footer lists what changed; nothing here restores or commits them. Before a commit on the
laptop: git checkout -- backend/tests/fixtures/
"""
import argparse
import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

BROWSER_ONLY = {"browser_check.js", "help_browser_check.js", "look_check.js", "map_browser_check.js", "ui_audit.js"}
KEYS = ("HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN", "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY",
        "SMTP_USER", "SMTP_PASSWORD", "DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "MAP_GATE")
COUNT = re.compile(r"(\d+) passed, (\d+) failed")
ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def harnesses(args):
    js = sorted(f for f in glob.glob(os.path.join(HERE, "*.js")) if os.path.basename(f) not in BROWSER_ONLY)
    py = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    out = [(f, [args.node, f]) for f in js] + [(f, [args.py, f]) for f in py]
    out.append((os.path.join(HERE, "http_smoke.py"), [args.smoke_py, os.path.join(HERE, "http_smoke.py")]))
    if args.only:
        out = [h for h in out if os.path.splitext(os.path.basename(h[0]))[0] in args.only]
    return out


def child_env():
    env = dict(os.environ)
    for k in KEYS:
        env.pop(k, None)
    env["PYTHONUTF8"] = "1"
    if not env.get("NODE_PATH"):
        npm = shutil.which("npm")
        if npm:
            root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, shell=(os.name == "nt"))
            env["NODE_PATH"] = root.stdout.strip()
    return env


def check_offline():
    for host in ("api.mapbox.com", "router.hereapi.com"):
        try:
            socket.create_connection((host, 443), timeout=5).close()
        except OSError as e:
            print(f"offline: {host} unreachable ({e.__class__.__name__}) — good")
            continue
        print(f"offline: {host} IS reachable. --require-offline expects no route out; stopping.")
        sys.exit(2)


def run_one(path, cmd, env, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=timeout)
        out, rc = (p.stdout + p.stderr).decode("utf-8", errors="replace"), p.returncode
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", errors="replace")
        out += f"\nrun_suite: TIMEOUT after {timeout}s"
        rc = "timeout"
    except OSError as e:
        out, rc = f"run_suite: could not start {cmd[0]!r}: {e}", "no-start"
    secs = time.time() - t0
    counts = COUNT.findall(out)
    passed, failed = (int(counts[-1][0]), int(counts[-1][1])) if counts else (None, None)
    why = []
    if rc != 0:
        why.append(f"exit {rc}")
    if passed is None:
        why.append("no count line")
    elif failed:
        why.append(f"{failed} failed")
    elif passed == 0:
        why.append("0 passed")
    if "SKIPPED" in out:
        why.append("SKIPPED")
    return {"name": os.path.basename(path), "passed": passed, "failed": failed, "secs": secs,
            "ok": not why, "why": ", ".join(why), "out": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--py", default=sys.executable, help="Python for test_*.py (no FastAPI)")
    ap.add_argument("--smoke-py", default=None, help="Python with backend/requirements.txt, for http_smoke.py")
    ap.add_argument("--node", default="node")
    ap.add_argument("--only", nargs="*", help="harness names without extension, e.g. parse_map test_users")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds per harness")
    ap.add_argument("--require-offline", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="print every harness's output, not only failures")
    args = ap.parse_args()
    if not args.smoke_py:
        for cand in (os.path.join(ROOT, ".venv-smoke", "Scripts", "python.exe"),
                     os.path.join(ROOT, ".venv-smoke", "bin", "python")):
            if os.path.exists(cand):
                args.smoke_py = cand
                break
        else:
            args.smoke_py = args.py   # http_smoke.py then reports SKIPPED, which counts as a failure

    if args.require_offline:
        check_offline()
    env = child_env()
    results = []
    for path, cmd in harnesses(args):
        r = run_one(path, cmd, env, args.timeout)
        results.append(r)
        shown = r["out"] if (args.verbose or ACTIONS or not r["ok"]) else ""
        if ACTIONS:
            print(f"::group::{r['name']} — {'ok' if r['ok'] else 'FAIL'} ({r['passed']} passed)")
        if shown:
            print(shown.rstrip())
        if ACTIONS:
            print("::endgroup::")
        mark = "ok  " if r["ok"] else "FAIL"
        print(f"{mark} {r['name']:<28} {r['passed'] if r['passed'] is not None else '-':>6} passed"
              f"  {r['secs']:6.1f}s  {r['why']}", flush=True)

    bad = [r for r in results if not r["ok"]]
    total = sum(r["passed"] or 0 for r in results)
    rows = [f"{r['name']:<28} {str(r['passed']) if r['passed'] is not None else '-':>6} / "
            f"{str(r['failed']) if r['failed'] is not None else '-':<4} {'' if r['ok'] else 'FAIL: ' + r['why']}"
            for r in results]
    line = "=" * 64
    print("\n" + line + "\nPer-harness counts (passed / failed)\n" + line)
    print("\n".join(rows))
    print(line)
    print(f"{len(results)} harnesses, {total:,} assertions passed, {len(bad)} harness(es) failing")

    changed = ""
    if shutil.which("git"):
        changed = subprocess.run(["git", "status", "--porcelain", "--", "backend/tests/fixtures"], cwd=ROOT,
                                 capture_output=True, text=True).stdout.rstrip()
    if changed:
        print("Fixtures rewritten by the harnesses (not restored, not committed):\n" + changed)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### Suite: {len(results)} harnesses, {total:,} assertions, "
                     f"{'all green' if not bad else str(len(bad)) + ' failing'}\n\n")
            fh.write("| Harness | Passed | Failed | |\n|---|---:|---:|---|\n")
            for r in results:
                fh.write(f"| {r['name']} | {r['passed'] if r['passed'] is not None else '-'} | "
                         f"{r['failed'] if r['failed'] is not None else '-'} | "
                         f"{'' if r['ok'] else 'FAIL: ' + r['why']} |\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
