"""
smoke_bulletin_kept.py — the REAL app: the monthly bulletin's page, its leaflet page and the leaflet PDF are kept once built
(11 Nov 2026, card A-F4 on John's page "Everything left"; branch claude/bulletin-print-fixes).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_bulletin_kept.py

On 11 Nov the bulletin's page took 16-21 s on EVERY open on live and the leaflet PDF 45 s on every press, because each was
built afresh; the newsletter PDF was already kept (`_staff_bytes`). This boots `main.app` (TestClient, middleware included)
on a scratch SQLite database, signs in with a planner code and counts the builds (`bulletin_doc.sheet` calls):

  * two opens of /bulletin/?month=10 build once; the bytes are the same;
  * a write to the plan (the data version moves) builds afresh: a reader never gets an older plan than the one approved;
  * another month is its own build; the leaflet page and the leaflet PDF are kept the same way;
  * a build whose map fell back to the schematic (basemap.MISSES moved) is served but never kept, as the PDF's rule;
  * still staff only: no sign-in answers 401 and builds nothing.

NOT covered: PostgreSQL, Mapbox (no token: every map is the schematic, so the "kept" checks count builds with MISSES held
still), live timings (after the merge, read only).
run_suite.py runs every backend/tests/smoke_*.py with --smoke-py.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, HERE)

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_bulletin_kept.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_bkept_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "MAP_GATE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({"PLANNER_CODE": "plan-code-xyz", "ADMIN_CODE": "admin-code-xyz", "IPT1_CODE": "north-code-xyz",
                   "MAP_PASSWORD": "map-pass-xyz", "GATE_SECRET": "gate-secret-for-tests-only", "WAYSCOPE_WARM_CACHE": "0"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "bkept.db")
import main  # noqa: E402
import basemap  # noqa: E402
import bulletin_doc  # noqa: E402
import read_cache  # noqa: E402
from portable import pin_today, DEMO_AS_OF, remove_scratch_db  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ok  ", label)
    else:
        FAIL.append(f"{label} {extra}".strip())
        print("  FAIL", label, extra)


BUILDS = {"n": 0, "miss": False}
_sheet = bulletin_doc.sheet


def counting_sheet(*a, **k):
    BUILDS["n"] += 1
    out = _sheet(*a, **k)
    if BUILDS["miss"]:
        basemap.MISSES[0] += 1          # as if Mapbox had refused the picture: the map is the schematic stand-in
    return out


bulletin_doc.sheet = counting_sheet
PLAN = {"X-Access-Code": "plan-code-xyz"}


def opens(c, path, headers=PLAN):
    before = BUILDS["n"]
    r = c.get(path, headers=headers)
    return r, BUILDS["n"] - before


with TestClient(main.app, base_url="https://testserver") as c:
    read_cache.clear()
    r0, b0 = opens(c, "/bulletin/?month=10", headers={})
    ok("🔴 still staff only: no sign-in answers 401 and builds nothing", r0.status_code == 401 and b0 == 0, f"{r0.status_code} {b0}")

    r1, b1 = opens(c, "/bulletin/?month=10")
    r2, b2 = opens(c, "/bulletin/?month=10")
    ok("⭐ the bulletin page: the first open builds it, the second is served kept (one build)",
       r1.status_code == 200 and r2.status_code == 200 and b1 == 1 and b2 == 0, f"{r1.status_code} {b1} {b2}")
    ok("the kept page is the same page, as HTML", r1.content == r2.content and "text/html" in r2.headers.get("content-type", "")
       and b"<html" in r2.content[:400].lower())
    ok("...and it still says no-store to the browser (kept on the server, never in a shared cache)",
       r2.headers.get("cache-control") == "no-store")

    db.bump_data_version()
    r3, b3 = opens(c, "/bulletin/?month=10")
    ok("⭐ a write to the plan in between: the next open builds afresh (never an older plan)", r3.status_code == 200 and b3 == 1, str(b3))

    r4, b4 = opens(c, "/bulletin/?month=11")
    r5, b5 = opens(c, "/bulletin/?month=11")
    ok("another month is its own build, then kept", b4 == 1 and b5 == 0, f"{b4} {b5}")

    r6, b6 = opens(c, "/bulletin/leaflet/?month=10")
    r7, b7 = opens(c, "/bulletin/leaflet/?month=10")
    ok("the leaflet page: built once, then kept", r6.status_code == 200 and b6 == 1 and b7 == 0 and r6.content == r7.content,
       f"{r6.status_code} {b6} {b7}")

    r8, b8 = opens(c, "/api/bulletin/leaflet.pdf?month=10")
    r9, b9 = opens(c, "/api/bulletin/leaflet.pdf?month=10")
    ok("⭐ the leaflet PDF: built once, then kept (it was rebuilt on every press)",
       r8.status_code == 200 and r9.status_code == 200 and b8 == 1 and b9 == 0 and r8.content == r9.content
       and r9.content[:5] == b"%PDF-", f"{r8.status_code} {b8} {b9}")
    ok("the leaflet PDF keeps its file name and no-store",
       "bulletin-one-page-" in r9.headers.get("content-disposition", "") and r9.headers.get("cache-control") == "no-store")

    BUILDS["miss"] = True
    db.bump_data_version()
    ra, ba = opens(c, "/bulletin/?month=10")
    rb, bb = opens(c, "/bulletin/?month=10")
    ok("⭐ a page whose map fell back to the schematic is served but never kept (the PDF's rule)",
       ra.status_code == 200 and ba == 1 and bb == 1, f"{ba} {bb}")
    rc, bc = opens(c, "/api/bulletin/leaflet.pdf?month=10")
    rd, bd = opens(c, "/api/bulletin/leaflet.pdf?month=10")
    ok("...and the same for the leaflet PDF", bc == 1 and bd == 1, f"{bc} {bd}")
    BUILDS["miss"] = False

_MS = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("source: the page, the leaflet page and the leaflet PDF go through _staff_bytes with the map rule",
   all(f'_staff_bytes("{n}"' in _MS for n in ("bulletin/page", "bulletin/leaflet-page", "bulletin/leaflet.pdf"))
   and _MS.count("keep=lambda: basemap.MISSES[0] == misses") >= 4)

print()
for f_ in FAIL:
    print("  FAIL:", f_)
print(f"\n{PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
