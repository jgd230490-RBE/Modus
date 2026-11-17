"""
smoke_tools_abnormal.py — the REAL app serving the abnormal load adviser (claude/tools-abnormal-adviser, 17 Nov 2026).

    python backend/tests/smoke_tools_abnormal.py      (in .venv-smoke)

  1. /tools/abnormal-load and /tools/abnormal-load.js answer an outsider with no cookie, the gate on, with every security
     header and no cookie set; the page carries no demo bar on the fictional demo deployment.
  2. POST /api/tools/abnormal-load answers the typed load with the page's words, equal to tools_abnormal.answer's, and
     not the rules' staff lines; every refusal is a 400 with one sentence; the trap answers and does nothing.
  3. Its limit refuses past its count with the limit's sentence (429), per address.
  4. Nothing is stored: every table's row count, the audit trail and the data version are the same after many checks.

NOT covered: PostgreSQL (SQLite only), a browser (the UI audit walks the page), Render's proxy.
"""
import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_tools_abnormal.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_tooladv_")
for v in ("DATABASE_URL", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_LEADS",
          "OS_MAPS_KEY", "LANDING_URL"):
    os.environ.pop(v, None)
os.environ.update({
    "TENANT_ID": "wolds-link-demo",
    "ADMIN_TOKEN": "adm-token-tooladv",
    "PLANNER_CODE": "plan-code-tooladv",
    "MAP_PASSWORD": "map-pass-tooladv",
    "GATE_SECRET": "gate-secret-for-tests-only",
    "WAYSCOPE_WARM_CACHE": "0",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "tooladv.db")
import main  # noqa: E402
import security_headers  # noqa: E402
import tools_abnormal  # noqa: E402
import tools_public  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:600])


BASE = "https://testserver"
PATH = "/api/tools/abnormal-load"


def clean(resp):
    return all(k.lower() in (h.lower() for h in resp.headers.keys()) for k in security_headers.HEADERS) \
        and "set-cookie" not in resp.headers


def counts():
    import sqlite3
    con = sqlite3.connect(db._SQLITE_PATH)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        con.close()


MOVE = (tools_abnormal.london_today() + datetime.timedelta(days=30))
if MOVE > tools_abnormal.last_moving_day():          # after 2028 the shipped holidays end: the refusal is the answer
    MOVE = None
BODY = dict(width_m="4.2", length_m="27", height_m="4.6", gross_t="76", max_axle_t="11", axle_count="7",
            date=MOVE.isoformat() if MOVE else "", axle_spacings_m="",          # as the page sends it (Q1: no where, no band)
            indivisible=True, website="")
HDR = {"X-Forwarded-For": "203.0.113.50", "Content-Type": "application/json"}

with TestClient(main.app, base_url=BASE) as anon:
    ok("0. the outsider holds no cookie", not anon.cookies)

    # ---- 1. the page and its script ------------------------------------------------------------------------------ #
    r = anon.get("/tools/abnormal-load")
    html = r.text
    ok("1. ⭐ /tools/abnormal-load answers an outsider with no cookie, the gate on", r.status_code == 200
       and r.headers.get("content-type", "").startswith("text/html"), str(r.status_code))
    ok("1. ...every security header, no-cache, no cookie set", clean(r) and r.headers.get("cache-control") == "no-cache")
    ok("1. ⭐🔴 no demo bar on the fictional demo deployment, no sign-in", "DEMO" not in html and "Fictional scheme" not in html
       and "Sign in" not in html)
    ok("1. the page is the file", r.content == (ROOT / "frontend/tools/abnormal-load.html").read_bytes())
    r = anon.get("/tools/abnormal-load.js")
    ok("1. ⭐ its own script answers, as a script, and is the file", r.status_code == 200
       and r.headers.get("content-type", "").startswith("text/javascript") and clean(r)
       and r.content == (ROOT / "frontend/tools/abnormal-load.js").read_bytes(), str(r.status_code))
    for path in ("/tools/abnormal-load.html", "/tools/abnormal-load.js.map", "/tools/other.js", "/tools/index.js"):
        ok(f"1. 🔴 {path} is a 404", anon.get(path, follow_redirects=False).status_code == 404)

    before = counts()
    ver0 = db.data_version() if hasattr(db, "data_version") else None

    # ---- 2. the answer --------------------------------------------------------------------------------------------- #
    main.TOOLS_ABNORMAL_LIMIT.reset()
    r = anon.post(PATH, json=BODY, headers=HDR)
    ok("2. ⭐ the open call answers an outsider with no cookie", r.status_code == 200 and "set-cookie" not in r.headers,
       f"{r.status_code} {r.text[:300]}")
    ok("2. ...never kept by a browser or proxy (no-store), with every security header",
       r.headers.get("cache-control") == "no-store" and clean(r), str(dict(r.headers)))
    data = r.json() if r.status_code == 200 else {}
    want = tools_abnormal.answer(BODY)["page"] if MOVE else None
    ok("2. ⭐ the answer is the page's words, the same as tools_abnormal.answer", data.get("page") == want, str(data)[:300])
    ok("2. 🔴 ...and only those: not the rules' staff lines, notes or flags", set(data) == {"ok", "page"}
       and "STGO Sch" not in r.text and "No escort is planned" not in r.text)
    if want:
        ok("2. the drawn load reads as card 3's class and rows", want["head"] == "STGO Category 2"
           and [k for k, _ in want["rows"]] == ["Police", "Road and bridge authorities", "Network Rail", "Attendant",
                                                 "Markers", "Speeds", "Escort", "Height"])
    for label, change, say in (("no width", {"width_m": ""}, "Type the width in metres."),
                               ("axles 1", {"axle_count": "1"}, "Type the number of axles: 2 or more."),
                               ("past", {"date": "2020-01-01"}, "Pick a moving day from today on."),
                               ("2029", {"date": "2029-03-01"},
                                "Pick a moving day up to 31 December 2028: the bank holidays held here end then."),
                               ("where", {"where": "france"}, "Pick England and Wales, or Scotland.")):
        r = anon.post(PATH, json=dict(BODY, **change), headers=HDR)
        ok(f"2. refusal {label}: a 400 with one sentence and nothing else", r.status_code == 400
           and r.json() == {"detail": {"say": say}} and clean(r), f"{r.status_code} {r.text[:200]}")
    r = anon.post(PATH, content=b"not json", headers=HDR)
    ok("2. a body that is not JSON is a 400 with a sentence", r.status_code == 400 and "say" in r.json().get("detail", {}))
    r = anon.post(PATH, json=dict(BODY, website="http://spam.example"), headers=HDR)
    ok("2. ⭐ the trap filled: answers as if it worked, works out nothing", r.status_code == 200 and r.json() == {"ok": True})
    r = anon.get(PATH)
    ok("2. a GET is not served", r.status_code in (404, 405))

    # ---- 3. the limit ------------------------------------------------------------------------------------------- #
    main.TOOLS_ABNORMAL_LIMIT.reset()
    n = tools_abnormal.CHECKS_PER_HOUR
    codes = [anon.post(PATH, json=BODY, headers={"X-Forwarded-For": "198.51.100.7"}).status_code for _ in range(n)]
    ok(f"3. {n} checks from one address in an hour are answered", all(c in (200, 400) for c in codes) and len(codes) == n,
       str(sorted(set(codes))))
    r = anon.post(PATH, json=BODY, headers={"X-Forwarded-For": "198.51.100.7"})
    ok("3. ⭐ the next is refused with the limit's sentence (429)", r.status_code == 429
       and r.json() == {"detail": {"say": "Too many checks from this connection. Please try again in an hour."}}, r.text[:200])
    r = anon.post(PATH, json=BODY, headers={"X-Forwarded-For": "198.51.100.8"})
    ok("3. ...while another address is still answered", r.status_code in (200, 400), str(r.status_code))
    main.TOOLS_ABNORMAL_LIMIT.reset()

    # ---- 4. nothing stored ------------------------------------------------------------------------------------- #
    after = counts()
    ok("4. ⭐🔴 nothing stored: every table's row count is the same after the checks", before == after,
       str({k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}))
    ok("4. 🔴 ...the audit trail included", before.get("audit_log") == after.get("audit_log"))
    if ver0 is not None:
        ok("4. 🔴 ...and the data version did not move (no kept read emptied)", db.data_version() == ver0)

shutil.rmtree(TMP, ignore_errors=True)
print()
for f in FAIL:
    print("  FAIL:", f)
print(f"smoke_tools_abnormal.py: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
