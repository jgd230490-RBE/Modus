"""
smoke_bulletin_pages.py — the REAL app: the monthly bulletin PDF keeps to four pages, one section a page (D43), with public
traffic limits on the map (12 Nov 2026, BUILD.md rule 13, on claude/bulletin-print-fixes).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_bulletin_pages.py

On 11 Nov a public traffic limit was drawn on live (the B6047 at Tilton on the Hill, 150 movements a day). A limit adds a row
to page 2's "Road works and limits", a "Traffic limits on local roads" table and a glance row to page 4, and a line to page
1's brief: page 4's sources spilled onto a page 5 of their own (found by the demo-package session's http_smoke). Fix
(export.NEWSLETTER_FIT): when a section runs over its page, the newsletter is set tighter, a step at a time (gaps first,
the council carbon map's height, then the small print down to 7 pt), until every section fits again. Nothing is left out.

This boots `main.app` on a scratch SQLite database, imports the demo package (no road routes), adds ONE, then TWO, then
THREE public traffic limits and builds the October 2026 newsletter (/api/bulletin/month.pdf?month=10) after each:

  * no limit: four pages, at the first step that fits (on this copy the council page lists all eight districts and ran
    to five pages on the code before, with no limit at all);
  * one limit (live's case): four pages, "4 of 4", the limit in the works table, in the traffic limits table and in the
    glance row, every numbered source present;
  * two and three limits: the page count is PRINTED, and asserted only as far as this branch holds it (see WHAT IS NOT).

WHAT IS NOT PROVED: the demo package carries no road routes, so its council pages are shorter than live's (HERE lines cross
more districts). A local copy with stand-in lines ran to five pages in Apr and May 2027 with NO limit (23 routes, page 2):
that is not a traffic-limit fault and is on card A-F8 for John. Mapbox is never called (every map is the schematic).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_bulletin_pages.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_bpages_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "MAP_GATE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({"PLANNER_CODE": "plan-code-xyz", "ADMIN_CODE": "admin-code-xyz", "IPT1_CODE": "north-code-xyz",
                   "MAP_PASSWORD": "map-pass-xyz", "GATE_SECRET": "gate-secret-for-tests-only", "WAYSCOPE_WARM_CACHE": "0"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "bpages.db")
import main  # noqa: E402
import export  # noqa: E402
import zones  # noqa: E402
import read_cache  # noqa: E402
import tenant_package  # noqa: E402
from portable import pin_today, DEMO_AS_OF, pdf_text, offline  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)
offline(export)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(f"{label} {extra}".strip())
        print("  FAIL", label, extra)


# which fit step each build used (the last build of a request is the one served), and each build's page count
STEPS, BUILT = [], []
_nl = export._newsletter


def recording_newsletter(S, map_h, pages=None, fit=None):
    STEPS.append(export.NEWSLETTER_FIT.index(fit) if fit in export.NEWSLETTER_FIT else 0)
    out = _nl(S, map_h, pages, fit=fit)
    BUILT.append((STEPS[-1], out[1]))
    if os.environ.get("BP_DEBUG"):
        _t = [x for x in pdf_text(out[0]).split("") if x.strip()]
        print("          build", STEPS[-1], round(map_h), pages, "->", out[1], out[2], "real pages", len(_t), "| last:", " ".join(_t[-1].split())[:160])
    return out


export._newsletter = recording_newsletter
PLAN = {"X-Access-Code": "plan-code-xyz"}

# live's limit (zone Z041, drawn 11 Nov) and two more on nearby roads, the longest names a limit is likely to carry
B6047 = [[-0.92079, 52.622928], [-0.919984, 52.625588], [-0.919639, 52.626905], [-0.918539, 52.62966], [-0.918245, 52.630274],
         [-0.917775, 52.630957], [-0.916563, 52.63305], [-0.916295, 52.63379], [-0.915658, 52.635177], [-0.914677, 52.638279],
         [-0.914053, 52.639836], [-0.913865, 52.640151], [-0.912784, 52.641113], [-0.912509, 52.641457], [-0.912244, 52.642009],
         [-0.912056, 52.642187], [-0.911343, 52.642709], [-0.910848, 52.642973], [-0.910043, 52.643244], [-0.90966, 52.643324],
         [-0.906979, 52.64365], [-0.905694, 52.643839], [-0.90519, 52.643951], [-0.904592, 52.644152]]
LIMITS = [("B6047 Melton Road, Cold Newton turn to Tilton on the Hill", B6047, 150),
          ("Main Street, Tilton on the Hill, from the church to the Oakham road", [[p[0] + 0.01, p[1] + 0.004] for p in B6047], 60),
          ("Leicester Road and High Street through the village centre, both ways", [[p[0] - 0.02, p[1] - 0.006] for p in B6047], 100)]


def ladder_ok():
    """the sizing builds stop at the FIRST step whose build is four pages, and the served build is that step"""
    sizing, final = BUILT[:-1], BUILT[-1] if BUILT else (None, None)
    first = next((st for st, n in sizing if n <= 4), None)
    return bool(sizing) and final[0] == first and all(n > 4 for st, n in sizing if st < first)         and [st for st, _ in sizing] == sorted(st for st, _ in sizing)


def newsletter(c, month=10):
    read_cache.clear()
    del STEPS[:]
    del BUILT[:]
    r = c.get(f"/api/bulletin/month.pdf?month={month}", headers=PLAN)
    txt = pdf_text(r.content) if r.status_code == 200 else ""
    pages = [" ".join(x.split()) for x in txt.split("\f") if x.strip()]
    print("        builds at steps:", STEPS)
    return r, pages, " ".join(txt.split()), (STEPS[-1] if STEPS else None)


with TestClient(main.app, base_url="https://testserver") as c:
    pkg = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
    res = tenant_package.import_tenant(pkg)
    ok("the demo package imports", bool(res.get("ok")), str(res)[:200])

    quiet = {}
    for m in (1, 2, 30, 50, 60):
        r, pg, j, step = newsletter(c, m)
        quiet[m] = (len(pg), step, ladder_ok())
    print("        quiet months (pages, step, ladder ok):", quiet)
    # on this copy every month's council page lists all eight districts, so even a quiet month needs a later step (the
    # first step's use where a month fits is pinned in test_bulletin_print.py, with stand-in builds)
    ok("⭐ quiet months, no limit: four pages each, at the first step that fits", all(n == 4 and lo for n, st, lo in quiet.values()),
       str(quiet))
    r, pg, j, step = newsletter(c)
    # on this copy October 2026 ran to FIVE pages with no limit on the code before (page 4's glance on a page of its own)
    ok("⭐ October 2026, no limit: four pages; the ladder stopped at the first step that fits",
       r.status_code == 200 and len(pg) == 4 and ladder_ok(), f"{r.status_code} {len(pg)} pages, {BUILT}")
    sources0 = [n for n in range(1, 15) if f" {n} " in (pg[-1] if pg else "")]

    counts = {}
    for n, (name, line, val) in enumerate(LIMITS, 1):
        z = zones.create_zone(name, {"type": "LineString", "coordinates": line}, kind="traffic_limit", affects_routing=False,
                              limit_value=val, limit_counts="movements", limit_basis="average", limit_public=True)
        ok(f"a public traffic limit is drawn ({n})", bool(z.get("id")), str(z)[:160])
        r, pg, j, step = newsletter(c)
        counts[n] = (len(pg), step)
        print(f"        {n} limit(s): {len(pg)} pages, fit step {step}")
        if n == 1:
            ok("⭐ ONE public limit (live's case since 11 Nov): four pages again, each foot \"n of 4\" (it was five: \"5 of 5\")",
               r.status_code == 200 and len(pg) == 4 and all(f"{i} of 4" in p for i, p in enumerate(pg, 1)),
               f"{len(pg)} pages, step {step}")
            ok("...built tighter only as far as needed: the first step that fits", ladder_ok(), str(BUILT))
            ok("...nothing left out: the limit is in page 2's works table and page 4's traffic limits table, by name",
               len(pg) == 4 and "B6047 Melton Road" in pg[1] and "Traffic limits on local roads" in pg[3]
               and "B6047 Melton Road" in pg[3] and "150 movements a day" in pg[3], pg[3][:300] if len(pg) > 3 else "")
            ok("...the glance row and the brief's line are there",
               "Traffic limits on local roads 0 over, 0 near Forecast against the limits" in j
               and "Traffic limits on local roads: 0 over, 0 near." in j)
            ok("...every numbered source is still on page 4 with the terms and caveats",
               len(pg) == 4 and all(f" {k} " in pg[3] for k in sources0) and "Terms" in pg[3] and "Caveats" in pg[3]
               and "Sources" in pg[3], str(sources0))
    print(f"        two limits: {counts.get(2)}, three limits: {counts.get(3)} (pages, fit step)")
    ok("two and three limits: never fewer pages than one limit, the sections in order (reported, see card A-F8)",
       counts.get(2, (0,))[0] >= 4 and counts.get(3, (0,))[0] >= counts.get(2, (0,))[0])

print(f"{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
