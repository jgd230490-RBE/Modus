"""
smoke_tools_route_check.py — the REAL app serving the route check request (claude/tools-route-check-request, 16 Nov 2026).

    python backend/tests/smoke_tools_route_check.py        # .venv-smoke

Boots main.app with TestClient on a scratch SQLite database, gate ON, and asks as an OUTSIDER with no cookie:
the page answers (no demo bar, no cookie, every security header); the open call keeps one row and answers {"ok": true}
no-store with no cookie; a bad box answers 400 with {"detail": {"say": sentence}}; the trap keeps nothing and answers ok;
the sixth call from one address answers 429 with a sentence; no audit row is written and the data version does not move;
the email goes to John after the answer (the sender is stubbed: nothing real is sent); the admin CSV refuses an outsider
and a code sign-in and answers the admin token.
NOT covered: PostgreSQL, a real SMTP session, a browser, Render's proxy.
"""
import os
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
    print(f"smoke_tools_route_check.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_toolrc_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM",
          "DEMO_NOTIFY", "DEMO_LEADS", "OS_MAPS_KEY", "LANDING_URL"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-toolrc", "PLANNER_CODE": "plan-code-toolrc", "IPT1_CODE": "north-code-toolrc",
                   "MAP_PASSWORD": "map-pass-toolrc", "GATE_SECRET": "gate-secret-for-tests-only",
                   "WAYSCOPE_WARM_CACHE": "0"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "toolrc.db")
import main  # noqa: E402
import demo_request  # noqa: E402
import security_headers  # noqa: E402
import tools_route_check  # noqa: E402

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
URL = "/api/tools/route-check/request"
GOOD = {"from": "Harborough Rail Freight Terminal", "to": "Harborough Compound", "lorry": "Artic Flatbed (44t)", "loads": "90",
        "name": "Ada Example", "email": "ada@example.org", "company": "", "note": "", "website": ""}
HDR = {"X-Wayscope": "1", "CF-Connecting-IP": "203.0.113.50"}


def clean(resp):
    return all(k.lower() in (h.lower() for h in resp.headers.keys()) for k in SEC) and "set-cookie" not in resp.headers


def n_leads():
    return db.query("SELECT COUNT(*) AS n FROM tool_leads")[0]["n"]


SENT = []
demo_request.send = lambda m, s: SENT.append(m)            # nothing real is ever sent

with TestClient(main.app, base_url=BASE) as anon:
    ok("0. the outsider holds no cookie", not anon.cookies)
    tools_route_check.LIMIT.reset()

    r = anon.get("/tools/route-check")
    ok("1. ⭐ the page answers an outsider, gate ON: 200, html, no-cache, security headers, no cookie",
       r.status_code == 200 and r.headers.get("content-type", "").startswith("text/html")
       and r.headers.get("cache-control") == "no-cache" and clean(r), str(r.status_code))
    ok("1. ...no demo bar, no 'Fictional scheme', the heading and the form", "DEMO" not in r.text and "Fictional" not in r.text
       and "Which road should the lorries take?" in r.text and 'id="rc-form"' in r.text)
    r = anon.get("/tools/route-check.js")
    ok("1. ⭐ its own script is served beside the page: 200, javascript, no-cache, no cookie, the file's bytes",
       r.status_code == 200 and r.headers.get("content-type", "").startswith("text/javascript")
       and r.headers.get("cache-control") == "no-cache" and clean(r)
       and r.content == (ROOT / "frontend" / "tools" / "route-check.js").read_bytes())
    ok("1. ...a script with no page beside it is still a 404", anon.get("/tools/no-such-page.js").status_code == 404
       and anon.get("/tools/index.js").status_code == 404)

    ver0 = db.data_version()
    a0 = db.query("SELECT COUNT(*) AS n FROM audit_log")[0]["n"]
    r = anon.post(URL, json=GOOD, headers=HDR)
    ok("2. ⭐ a good request: 200 {ok: true}, no-store, no cookie, security headers",
       r.status_code == 200 and r.json() == {"ok": True} and r.headers.get("cache-control") == "no-store" and clean(r),
       f"{r.status_code} {r.text[:200]}")
    ok("2. ...one row kept, and the email went to nobody (no sender configured): marked unsent",
       n_leads() == 1 and db.query("SELECT status FROM tool_leads")[0]["status"] == "unsent: SMTP not configured" and not SENT)
    ok("2. 🔴 the row holds the hash of the edge's address, never the address",
       "203.0.113.50" not in str(db.query("SELECT * FROM tool_leads")) and len(db.query("SELECT ip_hash FROM tool_leads")[0]["ip_hash"]) == 32)
    ok("2. 🔴 no audit row and the data version did not move (a public send keeps the kept reads)",
       db.query("SELECT COUNT(*) AS n FROM audit_log")[0]["n"] == a0 and db.data_version() == ver0)

    # the email, with a sender configured: after the answer, to John, once
    for k, v in (("SMTP_USER", "s@example.org"), ("SMTP_PASSWORD", "pw-secret-toolrc"), ("DEMO_FROM", "Wayscope <hello@example.org>"),
                 ("DEMO_NOTIFY", "john@example.org")):
        os.environ[k] = v
    r = anon.post(URL, json=dict(GOOD, email="grace@example.org"), headers=dict(HDR, **{"CF-Connecting-IP": "203.0.113.51"}))
    ok("3. ⭐ with a sender set: 200, ONE email to John, row marked sent", r.status_code == 200 and len(SENT) == 1
       and SENT[0]["To"] == "john@example.org" and SENT[0]["Subject"] == "Route check request"
       and "grace@example.org" in SENT[0].get_content() and "pw-secret-toolrc" not in SENT[0].as_string()
       and db.query("SELECT status FROM tool_leads WHERE email = ?", ("grace@example.org",))[0]["status"] == "sent")
    for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
        os.environ.pop(k, None)

    # refusals and the trap
    n = n_leads()
    r = anon.post(URL, json=dict(GOOD, to=""), headers=dict(HDR, **{"CF-Connecting-IP": "203.0.113.52"}))
    ok("4. a bad box: 400 with the one sentence as detail.say, and nothing kept",
       r.status_code == 400 and r.json() == {"detail": {"say": "Type where the load ends."}} and n_leads() == n and clean(r))
    r = anon.post(URL, content="not json", headers=dict(HDR, **{"CF-Connecting-IP": "203.0.113.52", "Content-Type": "application/json"}))
    ok("4. a body that is not JSON: 400 and a sentence, never a trace", r.status_code == 400
       and isinstance(r.json().get("detail", {}).get("say"), str))
    r = anon.post(URL, json=dict(GOOD, website="http://spam"), headers=dict(HDR, **{"CF-Connecting-IP": "203.0.113.53"}))
    ok("4. 🔴 the trap: 200 {ok: true} as if it worked, nothing kept, nothing sent",
       r.status_code == 200 and r.json() == {"ok": True} and n_leads() == n and len(SENT) == 1)

    # the limit: five an hour per address
    tools_route_check.LIMIT.reset()
    codes = [anon.post(URL, json=dict(GOOD, email=f"p{i}@example.org"), headers=dict(HDR, **{"CF-Connecting-IP": "198.51.100.9"})).status_code
             for i in range(7)]
    ok("5. 🔴 the sixth call from one address is 429, and the seventh", codes == [200] * 5 + [429] * 2, str(codes))
    r = anon.post(URL, json=GOOD, headers=dict(HDR, **{"CF-Connecting-IP": "198.51.100.9"}))
    ok("5. ...the refusal is one sentence, no count", r.status_code == 429
       and r.json()["detail"]["say"].startswith("Too many") and r.headers.get("cache-control") == "no-store")
    ok("5. ...and another address is not held back", anon.post(URL, json=GOOD, headers=dict(HDR, **{"CF-Connecting-IP": "198.51.100.10"})).status_code == 200)
    ok("5. a visitor cannot choose the address the limit counts: a made-up forwarded-for entry does not reset it",
       anon.post(URL, json=GOOD, headers=dict(HDR, **{"CF-Connecting-IP": "198.51.100.9", "X-Forwarded-For": "1.2.3.4"})).status_code == 429)

    # the admin read
    r = anon.get("/api/admin/tool-leads.csv")
    ok("6. 🔴 the CSV refuses an outsider with no token", r.status_code == 403 and "ada@example.org" not in r.text)
    r = anon.get("/api/admin/tool-leads.csv?token=wrong")
    ok("6. ...and a wrong token", r.status_code == 403)
    r = anon.get("/api/admin/tool-leads.csv?token=adm-token-toolrc")
    ok("6. ⭐ ...and answers the admin token: CSV, an attachment, no-store, the rows, no address hash",
       r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
       and r.headers.get("cache-control") == "no-store" and r.text.startswith("created_at,kind,name,email,")
       and "ada@example.org" in r.text and "203.0.113" not in r.text
       and db.query("SELECT ip_hash FROM tool_leads LIMIT 1")[0]["ip_hash"] not in r.text)
    anon.cookies.clear()

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\nsmoke_tools_route_check: {PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
