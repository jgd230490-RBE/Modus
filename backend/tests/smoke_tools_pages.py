"""
smoke_tools_pages.py — the REAL app serving the public tool pages (claude/tools-shell, 16 Nov 2026).

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_tools_pages.py

It boots `main.app` with FastAPI's TestClient (lifespan and middleware included) on a scratch SQLite database, with the
gate ON (MAP_PASSWORD set, MAP_GATE unset) and staff codes set, and asks as an OUTSIDER with no cookie at all:

  1. on this branch, with the real frontend/tools/ folder: the shared files answer, no page does, and /tools, /tools/
     and every other name are a 404;
  2. with the folder pointed at a scratch copy holding the sample page (backend/tests/tools_sample/calculators.html, never
     shipped): the page answers, with every security header, Cache-Control no-cache, no Set-Cookie and no demo bar; the
     bar's links follow LANDING_URL; the map, the guide, the bulletin, the map's data and a staff call still refuse;
  3. a TEST-ONLY open call, /api/tools/_sample, registered on the app inside this process only (the shipped app has no
     /api/tools route yet), written the way the open-call rule says: its limit refuses after its count with
     {"detail": {"say": …}}, every answer is no-store with no Set-Cookie, and no call writes an audit row or empties
     a kept read (db.data_version does not move).

NOT covered: PostgreSQL (SQLite only), a browser (the UI audit walks the pages once one ships), Render's proxy (the
X-Forwarded-For address is sent by hand).
run_suite.py runs every backend/tests/smoke_*.py with --smoke-py.
"""
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
    from fastapi import Request
    from fastapi.testclient import TestClient
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_tools_pages.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_toolpages_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_LEADS",
          "OS_MAPS_KEY", "LANDING_URL"):
    os.environ.pop(v, None)
os.environ.update({
    "ADMIN_TOKEN": "adm-token-toolpages",
    "PLANNER_CODE": "plan-code-toolpages",
    "IPT1_CODE": "north-code-toolpages",
    "MAP_PASSWORD": "map-pass-toolpages",
    "GATE_SECRET": "gate-secret-for-tests-only",
    "WAYSCOPE_WARM_CACHE": "0",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "tools.db")
import main  # noqa: E402
import gate  # noqa: E402
import security_headers  # noqa: E402
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
SEC = [k for k in security_headers.HEADERS]


def clean(resp):
    """Every security header, and no cookie set."""
    return all(k.lower() in (h.lower() for h in resp.headers.keys()) for k in SEC) and "set-cookie" not in resp.headers


# ---- the test-only open call, written to the open-call rule (tools_public's header) -------------------------------- #
SAMPLE_LIMIT = tools_public.Limit("sample", 3, 3600)
SAMPLE_PATH = "/api/tools/_sample"


@main.app.post(SAMPLE_PATH)
async def _sample_tool(request: Request):
    tools_public.guard(request, SAMPLE_LIMIT)
    body = await request.json()
    if tools_public.trapped(body):
        return {"ok": True}
    try:
        loads = int(body.get("loads"))
    except Exception:
        tools_public.refuse(400, "Type the number of loads.")
    return {"ok": True, "loads": loads, "lorries": -(-loads // 24)}


with TestClient(main.app, base_url=BASE) as anon:
    ok("0. the outsider holds no cookie", not anon.cookies)

    # ---- 1. this branch as shipped: no page yet --------------------------------------------------------------------- #
    for name in ("tools.css", "tools.js"):
        r = anon.get("/tools/" + name)
        ok(f"1. ⭐ /tools/{name} answers an outsider with no cookie, the gate ON", r.status_code == 200
           and r.content == (ROOT / "frontend" / "tools" / name).read_bytes(), str(r.status_code))
        ok(f"1. ...with its type, no-cache, every security header and no cookie set",
           r.headers.get("content-type", "").startswith("text/css" if name.endswith("css") else "text/javascript")
           and r.headers.get("cache-control") == "no-cache" and clean(r), str(dict(r.headers)))
    for path in ("/tools", "/tools/", "/tools/index", "/tools/index.html", "/tools/calculators.html",
                 "/tools/README.md", "/tools/..%2Fmain.py", "/tools/%2e%2e/backend/main.py", "/tools/x/y", "/tools/Tools.css"):
        r = anon.get(path, follow_redirects=False)
        ok(f"1. 🔴 {path} is a 404 (no redirect, no listing, no coming-soon page)", r.status_code == 404 and clean(r),
           f"{r.status_code} {r.headers.get('location', '')}")
    # 17 Nov 2026 (claude/tools-abnormal-adviser): narrowed from "no page on this branch" — the tool branches add theirs
    ok("1. the shipped folder serves only the first opening's tool pages",
       set(tools_public.pages()) <= {"abnormal-load", "calculators", "route-check"}, str(tools_public.pages()))
    # NARROWED 16 Nov 2026 (claude/tools-route-check-request): the first tool pages ship
    ok("1. the shipped folder holds only the named tool pages", set(tools_public.pages()) <= {"calculators", "abnormal-load", "route-check"})

    # ---- 2. a page in the frame (the sample, from a scratch copy of the folder) ------------------------------------- #
    scratch = Path(TMP) / "tools"
    scratch.mkdir()
    for name in ("tools.css", "tools.js"):
        shutil.copy(ROOT / "frontend" / "tools" / name, scratch / name)
    shutil.copy(HERE / "tools_sample" / "calculators.html", scratch / "calculators.html")
    real_dir = tools_public.TOOLS_DIR
    tools_public.TOOLS_DIR = scratch
    try:
        r = anon.get("/tools/calculators")
        html = r.text
        ok("2. ⭐ a tool page answers an outsider with no cookie, the gate ON", r.status_code == 200
           and r.headers.get("content-type", "").startswith("text/html"), str(r.status_code))
        ok("2. ⭐🔴 ...with every security header, Cache-Control no-cache, and no cookie set",
           clean(r) and r.headers.get("cache-control") == "no-cache", str(dict(r.headers)))
        ok("2. the policy the page gets allows only the app and Google Fonts' stylesheet for its CSS",
           "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in r.headers.get("content-security-policy", ""))
        ok("2. 🔴 no demo bar, no demo notice, no sign-in on the page", "DEMO" not in html and "Fictional scheme" not in html
           and "Sign in" not in html and "/api/auth" not in html)
        ok("2. the bar links to the landing site by default", 'href="https://wayscope.co.uk/tools"' in html
           and 'href="https://wayscope.co.uk/#demo"' in html)
        os.environ["LANDING_URL"] = "https://landing.example.test"
        html2 = anon.get("/tools/calculators").text
        os.environ.pop("LANDING_URL", None)
        ok("2. ⭐ ...and follows LANDING_URL where it is set", 'href="https://landing.example.test/tools"' in html2
           and 'href="https://landing.example.test/#demo"' in html2 and 'href="https://wayscope.co.uk' not in html2)
        for path in ("/tools/calculators.html", "/tools/"):
            r = anon.get(path, follow_redirects=False)
            ok(f"2. 🔴 {path} is still a 404 with a page in the folder", r.status_code == 404, str(r.status_code))
        r = anon.get("/tools/calculators/", follow_redirects=False)
        ok("2. a page's address with a slash on the end goes to the page itself (Starlette's slash rule), nowhere else",
           r.status_code in (307, 308) and r.headers.get("location", "").endswith("/tools/calculators"), str(r.headers))
        r = anon.get("/tools/nothing-here/", follow_redirects=True)
        ok("2. 🔴 ...and a name not in the folder ends at a 404 either way", r.status_code == 404, str(r.status_code))
        r = anon.get("/brand/logo-header-on-dark.svg")
        ok("2. the bar's logo answers an outsider", r.status_code == 200 and b"<svg" in r.content[:400])
        ok("2. 🔴 an outsider got no cookie anywhere on the way", not anon.cookies, str(dict(anon.cookies)))

        # what must still refuse an outsider
        refusals = {"/map/": 401, "/help/": 401, "/bulletin/": 401, "/api/zones": 401, "/api/routes/R001/geometry": 401}
        for path, want in refusals.items():
            r = anon.get(path)
            ok(f"2. 🔴 {path} still refuses an outsider ({want})", r.status_code == want, str(r.status_code))
        for path in ("/api/admin/users", "/api/admin/audit", "/api/forecasts", "/api/clp/documents"):
            r = anon.get(path)
            ok(f"2. 🔴 the staff call {path} still refuses an outsider", r.status_code in (401, 403), str(r.status_code))
    finally:
        tools_public.TOOLS_DIR = real_dir

    # ---- 3. a test-only open call, written to the rule -------------------------------------------------------------- #
    def audit_rows():
        return int(db.query("SELECT COUNT(*) AS n FROM audit_log")[0]["n"])

    v0, a0 = db.data_version(), audit_rows()
    ip = {"X-Forwarded-For": "203.0.113.20"}
    answers = [anon.post(SAMPLE_PATH, json={"loads": 90}, headers=ip) for _ in range(3)]
    ok("3. ⭐ the open call answers an outsider with no cookie and no app header", all(r.status_code == 200 for r in answers)
       and answers[0].json() == {"ok": True, "loads": 90, "lorries": 4}, str([r.status_code for r in answers]))
    ok("3. ⭐ every answer is no-store, with every security header and no cookie set",
       all(r.headers.get("cache-control") == "no-store" and clean(r) for r in answers))
    r = anon.post(SAMPLE_PATH, json={"loads": 90}, headers=ip)
    ok("3. ⭐🔴 the fourth call from the same address is refused with one plain sentence",
       r.status_code == 429 and r.json() == {"detail": {"say": SAMPLE_LIMIT.say}} and clean(r), r.text[:200])
    r = anon.post(SAMPLE_PATH, json={"loads": 90}, headers={"X-Forwarded-For": "198.51.100.30"})
    ok("3. another address is not held up", r.status_code == 200, str(r.status_code))
    r = anon.post(SAMPLE_PATH, json={"loads": "lots"}, headers={"X-Forwarded-For": "198.51.100.31"})
    ok("3. a bad figure is refused with a sentence the shared script shows", r.status_code == 400
       and r.json() == {"detail": {"say": "Type the number of loads."}}, r.text[:200])
    r = anon.post(SAMPLE_PATH, json={"loads": 90, "website": "spam"}, headers={"X-Forwarded-For": "198.51.100.32"})
    ok("3. the trap box filled: answered as if it worked, nothing worked out", r.status_code == 200 and r.json() == {"ok": True})
    ok("3. ⭐🔴 no open call wrote an audit row or emptied a kept read", db.data_version() == v0 and audit_rows() == a0,
       f"version {v0}->{db.data_version()}, audit {a0}->{audit_rows()}")
    # the same call with a staff code: it changes nothing (the call reads no access), and the answer is the same
    r = anon.post(SAMPLE_PATH, json={"loads": 90}, headers={"X-Forwarded-For": "198.51.100.33", "X-Access-Code": "plan-code-toolpages"})
    ok("3. a staff code changes nothing about an open call's answer", r.status_code == 200
       and r.json() == {"ok": True, "loads": 90, "lorries": 4})
    ok("3. 🔴 the test-only route is not in the shipped list of open calls", SAMPLE_PATH not in tools_public.OPEN_ROUTES)

print(f"smoke_tools_pages: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
