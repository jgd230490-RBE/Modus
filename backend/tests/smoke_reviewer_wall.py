"""
smoke_reviewer_wall.py — the REAL app: what a client reviewer's session can reach. Wayscope, 31 Oct 2026 (task 4a, PR 3c;
mockup notes/clp-reviewers-mockup-1031/ card 8, "a new harness asks every address in the app as a reviewer and fails
unless it is one of the public or review ones").

    pip install -r backend/requirements.txt httpx      # .venv-smoke, or CI
    python backend/tests/smoke_reviewer_wall.py

It boots `main.app` with FastAPI's TestClient (lifespan and middleware included) on a scratch SQLite database, imports the
demo package, approves one CLP as Issue 1 and sends it to a client group, then signs a reviewer in THE WAY THE PAGE DOES
(invite link -> password -> two-step set-up -> the session cookie). Then, for EVERY /api route the app registers (read from
the app itself, so a route added later is swept too) except /api/auth/* and the review routes:

    the same request as NOBODY and as THE REVIEWER (cookie + the app's header) must answer the same status, and for a
    read the same body — once with no map cookie and once with the map password's cookie.

A reviewer who reached any staff read, or any write, would answer differently from nobody, and the run fails naming the
route. Required path, query and body values are made from the app's own schema; a CLP id is the one sent to the reviewer
(so a leak would show that CLP), a route the demo's R001, a location its first.

Then the review routes themselves: refused to nobody and to a staff code, the reviewer's list and the download (the
stored issue, byte for byte the staff download), and the sign-in that set no staff gate cookie.

NOT covered: PostgreSQL (SQLite only), real email (none is set up: the invite link comes back to the admin), a browser.
run_suite.py runs every backend/tests/smoke_*.py with --smoke-py.
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient
    from fastapi.routing import APIRoute
    import httpx  # noqa: F401
except Exception as e:  # the stubbed sandbox
    print(f"smoke_reviewer_wall.py: SKIPPED — real FastAPI/httpx not importable ({e.__class__.__name__})")
    print("0 passed, 0 failed")
    sys.exit(0)

TMP = tempfile.mkdtemp(prefix="modus_rvwall_")
for v in ("DATABASE_URL", "TENANT_ID", "ALLOW_DEMO_CODES", "HERE_API_KEY", "MAPBOX_TOKEN", "MAPBOX_PUBLIC_TOKEN",
          "GOOGLE_MAPS_API_KEY", "GOOGLE_STREETVIEW_KEY", "MAP_GATE", "SMTP_USER", "SMTP_PASSWORD", "DEMO_LEADS",
          "OS_MAPS_KEY", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({
    "ADMIN_TOKEN": "adm-token-rvwall",
    "PLANNER_CODE": "plan-code-rvwall",
    "IPT1_CODE": "north-code-rvwall",
    "MAP_PASSWORD": "map-pass-rvwall",
    "GATE_SECRET": "gate-secret-for-tests-only",
    "WAYSCOPE_WARM_CACHE": "0",
})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "wall.db")
import main  # noqa: E402
import gate  # noqa: E402
import users as _users  # noqa: E402
sys.path.insert(0, HERE)
from portable import pin_today, DEMO_AS_OF  # noqa: E402
_PINNED = pin_today(DEMO_AS_OF)

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


TOKEN = {"token": "adm-token-rvwall"}
PLAN = {"X-Access-Code": "plan-code-rvwall"}
W = {"X-Wayscope": "1"}
DEMO = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
BASE = "https://testserver"

with TestClient(main.app, base_url=BASE) as admin:
    r = admin.post("/api/admin/tenant/import", params=TOKEN, json=DEMO)
    ok("0. the demo package imports", r.status_code == 200, r.text[:200])
    r = admin.get("/api/clp/documents", headers=PLAN)
    clps = r.json()["clps"]
    target = next((c for c in clps if c["id"].startswith("auto-") and c["id"].endswith("-all")), None)
    ok("0. the demo lists its CLPs (a site's every-team CLP to send)", r.status_code == 200 and target, r.text[:200])
    CLP = target["id"]
    r = admin.post(f"/api/clp/documents/{CLP}/approve", json={"note": "For the client"}, headers=PLAN)
    ok("0. a planner approves it as Issue 1", r.status_code == 200 and r.json()["last_issue"]["no"] == 1, r.text[:200])
    r = admin.get("/api/admin/reviewers", params=TOKEN)
    ok("0. the demo's one fictional group is there, with no reviewer",
       r.status_code == 200 and [g["name"] for g in r.json()["groups"]] == ["Highways client (fictional)"]
       and r.json()["reviewers"] == [], r.text[:200])
    GID = r.json()["groups"][0]["id"]
    r = admin.post("/api/admin/reviewer-groups", params=TOKEN, json={"name": "Other client"})
    OTHER = [g["id"] for g in r.json()["groups"] if g["name"] == "Other client"][0]
    r = admin.post("/api/admin/reviewers", params=TOKEN,
                   json={"email": "rita.reviewer@example.org", "name": "Rita Reviewer", "group_id": GID})
    ok("0. an admin adds a reviewer; with no sender the invite link comes back",
       r.status_code == 200 and "#invite=" in r.json().get("link", "") and r.json()["user"]["kind"] == "reviewer", r.text[:200])
    RID = r.json()["user"]["id"]
    INV = r.json()["link"].split("#invite=", 1)[1]
    r = admin.post(f"/api/clp/documents/{CLP}/review-send", json={"groups": [GID], "issue_no": 1}, headers=PLAN)
    ok("0. the planner sends Issue 1 to the group", r.status_code == 200 and r.json()["sent"], r.text[:200])
    staff_doc = admin.get(f"/api/clp/documents/{CLP}/issues/1.docx", headers=PLAN)
    ok("0. the staff download of Issue 1", staff_doc.status_code == 200 and staff_doc.content[:2] == b"PK")
    LOC = DEMO["tables"]["locations"][0]["id"]

    # ---- the reviewer signs in as the page does ----------------------------------------------------------------- #
    rev = TestClient(main.app, base_url=BASE, raise_server_exceptions=False)
    r = rev.post("/api/auth/reset", json={"token": INV, "password": "a long reviewer passphrase"}, headers=W)
    ok("1. ⭐ the invite's password answers the two-step SET-UP step, no session yet",
       r.status_code == 200 and r.json().get("step") == "setup" and "wayscope_session=" not in r.headers.get("set-cookie", ""),
       r.text[:200])
    key = r.json()["key"].replace(" ", "")
    r = rev.post("/api/auth/setup", json={"ticket": r.json()["ticket"], "code": _users.totp_at(key, _users.totp_step())},
                 headers=W)
    sc = r.headers.get("set-cookie", "")
    ok("1. ⭐ two-step set up: the reviewer is signed in, the answer is the review page's",
       r.status_code == 200 and r.json().get("via") == "reviewer" and r.json().get("group_name") == "Highways client (fictional)"
       and r.json().get("role") is None and len(r.json().get("recovery_codes") or []) == 10 and "wayscope_session=" in sc,
       r.text[:300])
    ok("1. 🔴 the sign-in set NO gate cookie (no staff or map level)", gate.COOKIE + "=" not in sc, sc[:300])
    r = rev.get("/api/auth/me")
    ok("1. 🔴 /api/auth/me: signed in as a reviewer, with NO access",
       r.status_code == 200 and r.json()["signed_in"] and r.json()["access"] is None
       and r.json()["reviewer"]["name"] == "Rita Reviewer", r.text[:200])
    r = rev.get("/api/review/clps")
    ok("1. ⭐ the reviewer's list holds the CLP sent to the group", r.status_code == 200
       and [c["id"] for c in r.json()["clps"]] == [CLP], r.text[:200])

    # ---- the sweep ------------------------------------------------------------------------------------------------ #
    spec = main.app.openapi()
    comps = spec.get("components", {}).get("schemas", {})
    ids = {"clp_id": CLP, "issue_no": "1", "route_id": "R001", "location_id": LOC, "user_id": RID, "group_id": GID,
           "team_id": "IPT1", "token": "x"}

    def example(schema, depth=0):
        if depth > 6 or not isinstance(schema, dict):
            return None
        if "$ref" in schema:
            return example(comps.get(schema["$ref"].split("/")[-1], {}), depth + 1)
        for k in ("anyOf", "oneOf", "allOf"):
            if k in schema:
                opts = [o for o in schema[k] if o.get("type") != "null"] or schema[k]
                return example(opts[0], depth + 1)
        t = schema.get("type")
        if "enum" in schema:
            return schema["enum"][0]
        if t == "object" or "properties" in schema:
            req = schema.get("required", [])
            return {k: example(v, depth + 1) for k, v in (schema.get("properties") or {}).items() if k in req}
        if t == "array":
            return []
        if t == "integer":
            return 1
        if t == "number":
            return 1.0
        if t == "boolean":
            return False
        return "x"

    def build(path, op):
        url = path
        query = {}
        for p in op.get("parameters", []):
            name, where = p["name"], p["in"]
            val = ids.get(name)
            if val is None:
                val = example(p.get("schema", {}))
            if where == "path":
                url = url.replace("{" + name + "}", str(val))
            elif where == "query" and p.get("required"):
                query[name] = val
        body = None
        rb = op.get("requestBody")
        if rb:
            sch = (rb.get("content", {}).get("application/json", {}) or {}).get("schema")
            body = example(sch) if sch else None
        return url, query, body

    VOLATILE = re.compile(r'"(?:[a-z_]*_at|now|generated|elapsed[a-z_]*|took_ms|ms|time|server_time|uptime[a-z_]*)"\s*:\s*'
                          r'("[^"]*"|[0-9.eE+-]+|null)')

    def norm(resp):
        try:
            return VOLATILE.sub('"~":0', json.dumps(resp.json(), sort_keys=True))
        except Exception:
            return f"<{resp.headers.get('content-type', '')}:{len(resp.content)}>"

    def call(client, method, url, query, body, extra):
        h = dict(W, **extra)
        if body is not None:
            return client.request(method, url, params=query, json=body, headers=h)
        return client.request(method, url, params=query, headers=h)

    swept, diffs, review_routes = 0, [], []
    for passname in ("no map cookie", "map password cookie"):
        anon = TestClient(main.app, base_url=BASE, raise_server_exceptions=False)
        if passname == "map password cookie":
            anon.post("/api/map-auth", json={"password": "map-pass-rvwall"})
            rev.post("/api/map-auth", json={"password": "map-pass-rvwall"})
        for path, ops in sorted(spec["paths"].items()):
            if not path.startswith("/api/"):
                continue
            if path.startswith("/api/review/"):
                review_routes.append(path)
                continue
            if path.startswith("/api/auth"):
                continue
            for method, op in sorted(ops.items()):
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                url, query, body = build(path, op)
                a = call(anon, method.upper(), url, query, body, {})
                b = call(rev, method.upper(), url, query, body, {})
                swept += 1
                same = a.status_code == b.status_code
                if same and method == "get" and 200 <= a.status_code < 300:
                    same = norm(a) == norm(b)
                if not same:
                    diffs.append(f"{passname}: {method.upper()} {path} nobody {a.status_code} vs reviewer {b.status_code}")
        # the routes the schema leaves out (old paths kept working): called with no body
        for rt in main.app.routes:
            if isinstance(rt, APIRoute) and rt.path.startswith("/api/") and not rt.include_in_schema:
                url = rt.path
                for k, v in ids.items():
                    url = url.replace("{" + k + "}", str(v))
                for m in sorted(rt.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}):
                    a_, b_ = call(anon, m, url, {}, None, {}), call(rev, m, url, {}, None, {})
                    swept += 1
                    if a_.status_code != b_.status_code or (m == "GET" and a_.status_code < 300 and norm(a_) != norm(b_)):
                        diffs.append(f"{passname}: {m} {rt.path} nobody {a_.status_code} vs reviewer {b_.status_code}")
        anon.close()
    eligible = sum(1 for rt in main.app.routes if isinstance(rt, APIRoute) and rt.path.startswith("/api/")
                   and not rt.path.startswith(("/api/review/", "/api/auth"))
                   for m in rt.methods if m in ("GET", "POST", "PUT", "PATCH", "DELETE"))
    ok("2. the sweep reached every /api route but the auth and review ones (twice)", swept == 2 * eligible and eligible > 200,
       f"{swept} calls, {eligible} routes")
    ok("2. ⭐🔴 THE WALL: on every route a reviewer answers exactly as nobody signed in", diffs == [], "; ".join(diffs[:20]))
    r = rev.get("/api/auth/me")
    ok("2. ...and the reviewer was signed in the whole time", r.json().get("reviewer") is not None)

    # ---- the review routes ----------------------------------------------------------------------------------------- #
    # NARROWED 31 Oct 2026 (PR 3d): + the group's tasks and the reviewer's own deletes (four routes, three paths)
    ok("3. five review routes, no more", sorted(set(review_routes)) == sorted({
        "/api/review/clps", "/api/review/clps/{clp_id}", "/api/review/clps/{clp_id}/issues/{issue_no}.docx",
        "/api/review/clps/{clp_id}/comments", "/api/review/clps/{clp_id}/decision",
        "/api/review/clps/{clp_id}/tasks", "/api/review/clps/{clp_id}/tasks/{task_id}", "/api/review/clps/{clp_id}/notes/{item_id}"}),
       str(sorted(set(review_routes))))
    nobody = TestClient(main.app, base_url=BASE)
    ok("3. 🔴 nobody signed in gets nothing from them",
       all(nobody.get(u).status_code == 401 for u in ("/api/review/clps", f"/api/review/clps/{CLP}",
                                                       f"/api/review/clps/{CLP}/issues/1.docx")))
    ok("3. 🔴 nor does a staff code (the review page is a reviewer's only)",
       admin.get("/api/review/clps", headers=PLAN).status_code == 401)
    d = rev.get(f"/api/review/clps/{CLP}/issues/1.docx")
    ok("3. ⭐ the reviewer downloads Issue 1 exactly as approved", d.status_code == 200 and d.content == staff_doc.content)
    ok("3. 🔴 an issue never sent, or another CLP: 404",
       rev.get(f"/api/review/clps/{CLP}/issues/2.docx").status_code == 404
       and rev.get(f"/api/review/clps/{[c for c in clps if c['id'] != CLP][0]['id']}").status_code == 404)
    r = rev.post(f"/api/review/clps/{CLP}/comments", json={"words": "Please add the Saturday hours."})
    ok("3. 🔴 a reviewer's write without the app's header is refused", r.status_code == 403)
    r = rev.post(f"/api/review/clps/{CLP}/decision", json={"issue_no": 1, "decision": "returned",
                                                          "words": "Please add the Saturday hours."}, headers=W)
    ok("3. ⭐ the reviewer returns Issue 1 with a comment", r.status_code == 200 and r.json()["latest"]["state"] == "returned",
       r.text[:200])
    r = admin.get("/api/clp/documents", headers=PLAN)
    line = [c for c in r.json()["clps"] if c["id"] == CLP][0]["reviews"]
    ok("3. ⭐ the contractor's list shows it", line and line[0]["state"] == "returned" and line[0]["by"] == "Rita Reviewer")
    r = admin.get("/api/admin/audit", params=TOKEN)
    rows = r.json().get("rows") or r.json().get("audit") or r.json().get("events") or []
    txt = json.dumps(rows, ensure_ascii=False)
    ok("3. ⭐ the audit trail names the reviewer and the group for the download and the decision",
       "review-download" in txt and "Rita Reviewer <rita.reviewer@example.org> · Highways client (fictional)" in txt
       and f"/api/review/clps/{CLP}/decision" in txt, txt[:300])
    r = admin.patch(f"/api/admin/reviewer-groups/{GID}", params=TOKEN, json={"stopped": True})
    ok("3. 🔴 stopping the group signs the reviewer out at once",
       r.status_code == 200 and rev.get("/api/review/clps").status_code == 401 and rev.get("/api/auth/me").json()["signed_in"] is False)
    r = rev.post("/api/auth/signout", headers=W)
    ok("3. a reviewer's sign-out opens nothing (no map cookie set)", r.status_code == 200
       and gate.COOKIE + "=" not in (r.headers.get("set-cookie") or "").replace(f"{gate.COOKIE}=\"\"", ""), r.headers.get("set-cookie"))

print(f"smoke_reviewer_wall: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
