"""
28 Oct 2026 (pilot readiness phase 3, F3 a): an organisation's own deployment.

  backend/deployment.py            which settings a deployment has (names only) and what an organisation's must fix
  backend/check_deployment.py      the same in the hosting's shell, plus what the database holds
  backend/tools/check_pilot.py     the outside hand-over check (here against a fake deployment; http_smoke.py runs
                                   it against the real app)
  backend/tools/new_organisation.py  the two files for a new organisation: Render settings with fresh secrets, the steps

Run from the repo root:  python backend/tests/test_deployment.py

What it does not prove: Render itself (the region, "Add from .env", the custom domain, the certificate), Cloudflare,
the start-up line in a real service log, a real network answer (check_pilot's http_fetch is not called here). The
rehearsal on a throw-away Frankfurt service is the test of those (notes, session-1028-pilot-deploy.md).
"""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "tools"))
sys.path.insert(0, HERE)
os.environ.pop("DATABASE_URL", None)

import deployment  # noqa: E402
import check_pilot  # noqa: E402
import new_organisation as neworg  # noqa: E402

PASS, FAIL = 0, []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  ✓", label)
    else:
        FAIL.append(label)
        print("  ✗", label, "—", extra)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


GOOD = {
    "RENDER": "true", "DATABASE_URL": "postgresql://u:SECRETPW@dpg-x/acme", "TENANT_ID": "acme",
    "APP_URL": "https://acme.wayscope.co.uk", "FIRST_ADMIN_EMAIL": "jd@wayscope.co.uk",
    "GATE_SECRET": "GATESECRETVALUE", "MAP_PASSWORD": "MAPPWVALUE", "HERE_API_KEY": "HEREKEYVALUE",
    "MAPBOX_TOKEN": "pk.TOKENVALUE", "SMTP_USER": "jd@wayscope.co.uk", "SMTP_PASSWORD": "SMTPPWVALUE",
    "DEMO_FROM": "Wayscope <jd@wayscope.co.uk>",
}


def must(env, admins=1):
    return [w for lvl, w in deployment.problems(env, admins) if lvl == deployment.MUST]


def should(env, admins=1):
    return [w for lvl, w in deployment.problems(env, admins) if lvl == deployment.SHOULD]


def with_(**kw):
    e = dict(GOOD)
    for k, v in kw.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    return e


print("\n1. deployment.kind and the local case")
ok("no RENDER variable -> local", deployment.kind({}) == "local" and deployment.kind({"DEMO_LEADS": "1"}) == "local")
ok("on the hosting with DEMO_LEADS=1 -> demo", deployment.kind({"RENDER": "true", "DEMO_LEADS": "1"}) == "demo")
ok("on the hosting with DEMO_LEADS unset, blank or 0 -> organisation",
   all(deployment.kind({"RENDER": "true", "DEMO_LEADS": v}) == "organisation" for v in ("", "0", "no")))
ok("local: nothing is a problem, even with no database and a token",
   deployment.problems({"ADMIN_TOKEN": "x"}, admins=0) == [])
ok("local: the report is the one deployment: line", len(deployment.report_lines({}, 0)) == 1
   and deployment.report_lines({}, 0)[0].startswith("deployment: local"))

print("\n2. an organisation's deployment set up as the steps say")
ok("nothing must be fixed", must(GOOD) == [], str(must(GOOD)))
ok("nothing should be either", should(GOOD) == [], str(should(GOOD)))
_lines = deployment.report_lines(GOOD, 1)
ok("the report ends with the all-clear line", _lines[-1] == "deployment ✓ nothing that must be fixed", str(_lines))
ok("the first line names the kind, the tenant and the links' address",
   _lines[0].startswith("deployment: organisation · tenant acme · links https://acme.wayscope.co.uk · set: "), _lines[0])
_secret_values = [v for k, v in GOOD.items() if k not in ("RENDER", "TENANT_ID", "APP_URL")]
ok("🔴 no setting's VALUE is ever in the report (names only)",
   not any(v in l for v in _secret_values for l in _lines), str(_lines))
ok("the settings listed are named", all(n in _lines[0] for n in ("DATABASE_URL", "GATE_SECRET", "MAP_PASSWORD")))

print("\n3. what an organisation's deployment must fix")
ok("🔴 ADMIN_TOKEN set", any("ADMIN_TOKEN is set" in w for w in must(with_(ADMIN_TOKEN="t"))))
ok("🔴 a shared code set (named, never its value)",
   any("Shared codes are set (IPT3_CODE, PLANNER_CODE)" in w for w in must(with_(IPT3_CODE="c3", PLANNER_CODE="p")))
   and not any("c3" in w for w in must(with_(IPT3_CODE="c3"))))
ok("🔴 APP_URL missing", any("APP_URL is not set" in w for w in must(with_(APP_URL=None))))
ok("🔴 APP_URL not https", any("must start with https://" in w for w in must(with_(APP_URL="http://acme.wayscope.co.uk"))))
ok("🔴 APP_URL left as the demo's address (either name)",
   all(any("demo's address" in w for w in must(with_(APP_URL=u)))
       for u in ("https://app.wayscope.co.uk", "https://modus-web.onrender.com/")))
ok("🔴 GATE_SECRET missing", any("GATE_SECRET is not set" in w for w in must(with_(GATE_SECRET=None))))
ok("🔴 no DATABASE_URL on the hosting", any("DATABASE_URL is not set" in w for w in must(with_(DATABASE_URL=None))))
ok("🔴 no admin and no FIRST_ADMIN_EMAIL", any("nobody can sign in" in w for w in must(with_(FIRST_ADMIN_EMAIL=None), 0)))
ok("...but an existing admin needs no FIRST_ADMIN_EMAIL", must(with_(FIRST_ADMIN_EMAIL=None), 1) == [])
ok("...and an unknown admin count (None) does not guess", must(with_(FIRST_ADMIN_EMAIL=None), None) == [])
ok("🔴 ALLOW_DEMO_CODES on", any("ALLOW_DEMO_CODES" in w for w in must(with_(ALLOW_DEMO_CODES="yes"))))
ok("...ALLOW_DEMO_CODES blank or 0 is off", must(with_(ALLOW_DEMO_CODES="0")) == [] and must(with_(ALLOW_DEMO_CODES="")) == [])
ok("🔴 MAP_GATE off", all(any("MAP_GATE is off" in w for w in must(with_(MAP_GATE=v))) for v in ("off", "0", "false", "no")))
ok("...MAP_GATE on is not a problem", must(with_(MAP_GATE="on")) == [])
ok("a report with a must line has no all-clear line",
   not any("✓" in l for l in deployment.report_lines(with_(ADMIN_TOKEN="t"), 1))
   and any(l.startswith("deployment ✗ ADMIN_TOKEN") for l in deployment.report_lines(with_(ADMIN_TOKEN="t"), 1)))

print("\n4. what it should have")
ok("TENANT_ID missing or 'default'", all(any("TENANT_ID" in w for w in should(with_(TENANT_ID=v))) for v in (None, "default")))
ok("email not set up", any("Email is not set up" in w for w in should(with_(SMTP_PASSWORD=None))))
ok("MAP_PASSWORD missing (outside viewers refused) is a should, not a must",
   any("MAP_PASSWORD" in w for w in should(with_(MAP_PASSWORD=None))) and must(with_(MAP_PASSWORD=None)) == [])
ok("HERE and Mapbox keys", any("HERE_API_KEY" in w for w in should(with_(HERE_API_KEY=None)))
   and any("MAPBOX_TOKEN" in w for w in should(with_(MAPBOX_TOKEN=None))))
ok("a should line is marked ⚠ and the all-clear still shows",
   deployment.report_lines(with_(HERE_API_KEY=None), 1)[-1] == "deployment ✓ nothing that must be fixed"
   and any(l.startswith("deployment ⚠ HERE_API_KEY") for l in deployment.report_lines(with_(HERE_API_KEY=None), 1)))

print("\n5. the demo")
_demo = with_(DEMO_LEADS="1", ADMIN_TOKEN="t", PLANNER_CODE="p", APP_URL=None, GATE_SECRET=None)
ok("the demo may keep its token, codes and the default address while they are retired", deployment.problems(_demo, 1) == [])
ok("...but not an open gate, the demo codes or a file database",
   len(must(with_(DEMO_LEADS="1", MAP_GATE="off", ALLOW_DEMO_CODES="1", DATABASE_URL=None))) == 3)

print("\n6. check_deployment.py (the shell check) on a scratch database")
import db  # noqa: E402
from portable import remove_scratch_db  # noqa: E402
TMP = tempfile.mkdtemp(prefix="wayscope_deploy_")
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_users_db()
import users  # noqa: E402
import check_deployment  # noqa: E402
_f = check_deployment.database_facts()
ok("an empty deployment: sqlite, no admins, no data",
   _f == {"database": "sqlite (a file)", "admins": 0, "admins_two_step": 0, "staff_logins": 0, "locations": 0,
          "routes": 0}, str(_f))
_u, _e = users.create_user("jd@wayscope.co.uk", "JD", "admin")
users.create_user("lead@example.org", "Lead", "team", team="IPT1", kind="demo")
_f = check_deployment.database_facts()
ok("one admin without two-step; a demo login is not a staff login",
   _f["admins"] == 1 and _f["admins_two_step"] == 0 and _f["staff_logins"] == 1, str(_f))
_cl = check_deployment.lines(GOOD, _f)
ok("the database line sits second", _cl[1].startswith("database: sqlite (a file) · admin logins 1 (0 with two-step on)"), _cl[1])
ok("an admin without two-step is a warning on an organisation's deployment",
   any("has not set up two-step" in l for l in _cl), str(_cl))
ok("...printed above the all-clear line, which stays last (the rehearsal printed it after, 28 Oct)",
   _cl[-1] == "deployment ✓ nothing that must be fixed" and "has not set up two-step" in _cl[-2], str(_cl))
db.execute("UPDATE users SET totp_secret = ? WHERE id = ?", ("JBSWY3DPEHPK3PXP", _u["id"]))
_cl = check_deployment.lines(GOOD, check_deployment.database_facts())
ok("...gone once two-step is on", not any("two-step" in l and "⚠" in l for l in _cl) and "(1 with two-step on)" in _cl[1], str(_cl))
_saved_env = dict(os.environ)
try:
    os.environ.clear(); os.environ.update(with_(ADMIN_TOKEN="t"))
    os.environ.pop("DATABASE_URL")  # db was imported without it; the check reads the variable only
    _rc_bad = check_deployment.main(["check_deployment.py"])
    os.environ.clear(); os.environ.update(GOOD)
    _rc_good = check_deployment.main(["check_deployment.py"])
finally:
    os.environ.clear(); os.environ.update(_saved_env)
ok("exit 1 when something must be fixed, 0 when nothing must", _rc_bad == 1 and _rc_good == 0, f"{_rc_bad} {_rc_good}")
ok("🔴 it only reads: no write call in the module", not re.search(r"db\.(execute|insert)|INSERT|UPDATE|DELETE",
                                                                  read("backend/check_deployment.py")))

print("\n7. check_pilot.py against a fake deployment")
SEC = {n: "x" for n in check_pilot.HEADERS}
SEC["content-security-policy"] = "default-src 'self'; frame-ancestors 'self'"


def fake(over=None):
    over = over or {}

    def f(method, url, data=None, headers=None, timeout=30):
        path = re.sub(r"^https?://[^/]+", "", url) or "/"
        if url.startswith("http://"):
            return over.get("http", (301, {"location": "https://acme.wayscope.co.uk/api/health"}, ""))
        if path in over:
            return over[path]
        return {
            "/api/health": (200, {}, '{"status":"ok"}'),
            "/": (200, SEC, "<html>"),
            "/api/auth/me": (200, {"cache-control": "no-store"}, "{}"),
            "/api/admin/users": (403, {}, '{"detail":"admin access is not configured — set ADMIN_TOKEN"}'),
            "/api/public/demo-request": (303, {"location": "https://wayscope.co.uk/error.html"}, ""),
            "/map/": (401, {}, "<html>password"),
            "/help/": (401, {}, "<html>sign in"),
        }[path]
    return f


def res(rows):
    return [r for r, _ in rows]


_r = check_pilot.checks("https://acme.wayscope.co.uk", fetch=fake())
ok("an organisation's deployment as it should be: no FAIL", check_pilot.FAIL not in res(_r), str(_r))
ok("eleven rows: health, http, page, headers, framing, no-store, admin, form, map, guides, address", len(_r) == 11, str(_r))
ok("🔴 an address without https is refused before anything is asked",
   check_pilot.checks("http://acme.wayscope.co.uk", fetch=fake()) == [(check_pilot.FAIL, "The address must start with https://")])


def _boom(*a, **k):
    raise OSError("no route")


ok("no answer at all -> one FAIL row naming the error",
   res(check_pilot.checks("https://acme.wayscope.co.uk", fetch=_boom)) == [check_pilot.FAIL])
_tok = {"/api/admin/users": (403, {}, '{"detail":"bad or missing admin token"}')}
ok("🔴 a set ADMIN_TOKEN fails an organisation's check", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake(_tok))))
ok("...and is a note on the demo", check_pilot.FAIL not in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake(dict(_tok, **{"/api/public/demo-request": (303, {"location": "x/thanks.html"}, "")})),
    demo=True)))
ok("🔴 the form ON fails an organisation's check", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"/api/public/demo-request": (303, {"location": "x/thanks.html"}, "")}))))
ok("...and the form OFF fails the demo's", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake(), demo=True)))
ok("🔴 admin calls answering 200 fail", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"/api/admin/users": (200, {}, "[]")}))))
ok("🔴 the map opening without a password fails", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"/map/": (200, {}, "<html>map")}))))
ok("no map password set (503) is a note, not a failure", check_pilot.FAIL not in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"/map/": (503, {}, "not configured")}))))
ok("🔴 a missing security header fails and is named", any(
    r == check_pilot.FAIL and "missing permissions-policy" in w for r, w in check_pilot.checks(
        "https://acme.wayscope.co.uk", fetch=fake({"/": (200, {k: v for k, v in SEC.items() if k != "permissions-policy"}, "")}))))
ok("🔴 cached sign-in answers fail", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"/api/auth/me": (200, {"cache-control": "no-cache"}, "{}")}))))
ok("🔴 plain http not sent to https fails", check_pilot.FAIL in res(check_pilot.checks(
    "https://acme.wayscope.co.uk", fetch=fake({"http": (200, {}, "ok")}))))
_src = read("backend/tools/check_pilot.py")
ok("🔴 the form is tried with its trap field only (the app stores nothing for it)",
   'data=b"website=check-pilot"' in _src and "website" == __import__("demo_request").HONEYPOT)
ok("it sends no password, code or cookie", not re.search(r"(?i)password=|X-Access-Code|Cookie", _src.split("def checks")[1]))
ok("the address row says it is Render's edge, not the region (28 Oct: a Frankfurt service resolved to us-west1)",
   "it does not show the region" in _src)
ok("it never follows a redirect", "_NoRedirect" in _src and "return None" in _src)
ok("standard library only", not re.search(r"^import (requests|httpx)|^from (requests|httpx)", _src, re.M))

print("\n8. new_organisation.py")
_env = neworg.environment("acme", "jd@wayscope.co.uk", "John", mapbox="pk.test")
_keys = [l.split("=", 1)[0] for l in _env.strip().split("\n")]
ok("the settings to paste: Python, tenant, address, first admin, the two fresh secrets, Mapbox",
   _keys == ["PYTHON_VERSION", "TENANT_ID", "APP_URL", "FIRST_ADMIN_EMAIL", "FIRST_ADMIN_NAME", "GATE_SECRET", "MAP_PASSWORD",
             "MAPBOX_TOKEN"], str(_keys))
ok("TENANT_ID and APP_URL from the short name", "TENANT_ID=acme\n" in _env and "APP_URL=https://acme.wayscope.co.uk\n" in _env)
ok("🔴 never a token, a code, the lead form or a secret the demo holds",
   not any(k in _keys for k in ("ADMIN_TOKEN", "PLANNER_CODE", "ADMIN_CODE", "IPT1_CODE", "DEMO_LEADS", "ALLOW_DEMO_CODES",
                                "MAP_GATE", "HERE_API_KEY", "SMTP_PASSWORD", "DATABASE_URL")))
_e2 = neworg.environment("acme", "jd@wayscope.co.uk", "", mapbox="")
ok("no admin name and no Mapbox token -> those lines left out", "FIRST_ADMIN_NAME" not in _e2 and "MAPBOX_TOKEN" not in _e2)
_g = [l for l in _env.split("\n") if l.startswith("GATE_SECRET=")][0][12:]
_g2 = [l for l in _e2.split("\n") if l.startswith("GATE_SECRET=")][0][12:]
ok("🔴 GATE_SECRET fresh each time: 48 hex characters", re.fullmatch(r"[0-9a-f]{48}", _g) and _g != _g2)
_m = neworg.map_password()
ok("MAP_PASSWORD fresh, four groups of four, no look-alike characters",
   re.fullmatch(r"[a-z2-9]{4}(-[a-z2-9]{4}){3}", _m) and not set(_m) & set("01ilo") and _m != neworg.map_password(), _m)
ok("the Mapbox public token is read from map/config.js", neworg.mapbox_public_token().startswith("pk."))
_st = neworg.steps("acme", "Acme Rail", "jd@wayscope.co.uk")
ok("the steps name both services, the region, the release branch, the address",
   all(s in _st for s in ("wayscope-acme-db", "wayscope-acme", "Frankfurt (EU Central)", "Branch: pilot-release",
                          "acme.wayscope.co.uk", "Name acme", "DNS only (grey)")))
ok("🔴 the steps list what must never be set", "NEVER add: ADMIN_TOKEN" in _st and "DEMO_LEADS" in _st.split("NEVER add:")[1])
ok("the steps say the database takes no outside connection, and what to do with no custom-domain place free",
   "Access Control: no source listed" in _st and "skip C: set APP_URL to the address from step 10" in _st)
ok("the steps end with both checks and the end of the pilot",
   "check_pilot.py https://acme.wayscope.co.uk" in _st and "check_deployment.py" in _st and "THE END OF THE PILOT" in _st)
_ry = read("render.yaml")
ok("the build and start commands and the Python version are render.yaml's",
   f'buildCommand: "{neworg.BUILD}"' in _ry and f'startCommand: "{neworg.START}"' in _ry
   and f'value: "{neworg.PYTHON_VERSION}"' in _ry)
_rh = neworg.steps("rehearsal", "Rehearsal", "jd@wayscope.co.uk", branch="claude/pilot-deploy")
ok("a rehearsal may follow another branch, and the steps say it is one",
   "Branch: claude/pilot-deploy (a REHEARSAL" in _rh and "pilot-release" not in _rh.split("Branch:")[1].splitlines()[0])
ok("by default the steps say why it is not main", "Branch: pilot-release (not main" in _st)
ok("names: short names only", all(neworg.ORG_RE.match(o) for o in ("acme", "acme-rail", "a2b"))
   and not any(neworg.ORG_RE.match(o) for o in ("Acme", "a", "-acme", "acme-", "acme_rail", "1acme", "acme rail")))
ok("🔴 the repo is inside git (its files are refused there)", neworg.inside_git(ROOT) and neworg.inside_git(os.path.join(ROOT, "x")))
_out = os.path.join(TMP, "pilots", "acme")
ok("a folder outside git is not", not neworg.inside_git(_out))
ok("🔴 main refuses to write inside the checkout", neworg.main(["n", "acme", "Acme", "jd@wayscope.co.uk", "--out",
                                                              os.path.join(ROOT, "pilots-x")]) == 2
   and not os.path.exists(os.path.join(ROOT, "pilots-x")))
ok("main refuses a bad short name and a bad email", neworg.main(["n", "acme_rail", "A", "jd@w.co.uk", "--out", _out]) == 2
   and neworg.main(["n", "acme", "A", "not-an-email", "--out", _out]) == 2)
ok("main writes the two files", neworg.main(["n", "acme", "Acme Rail", "jd@wayscope.co.uk", "--out", _out]) == 0
   and sorted(os.listdir(_out)) == ["acme-render-environment.txt", "acme-steps.txt"])
ok("🔴 ...and will not overwrite the settings file (fresh secrets need a deliberate delete)",
   neworg.main(["n", "acme", "Acme Rail", "jd@wayscope.co.uk", "--out", _out]) == 2)

print("\n9. wiring and words")
_main = read("backend/main.py")
ok("start-up prints the deployment lines after the first admin", 0 < _main.find("users.ensure_first_admin()")
   < _main.find("deployment.report_lines(admins=users.count_admins())"))
ok("REVERSED: render.yaml no longer says admin calls are open while ADMIN_TOKEN is unset",
   "OPEN while it is unset" not in _ry and "ADMIN_TOKEN" in _ry)
_ex = read("env.example")
ok("REVERSED: env.example no longer says an unset ADMIN_TOKEN opens every admin endpoint",
   "is a no-op and EVERY admin endpoint is" not in _ex and "check_deployment.py" in _ex)
ok("the technical guide names both checks", all(s in read("frontend/help/technical/index.html")
                                               for s in ("check_pilot.py", "check_deployment.py", "new_organisation.py")))
ok("🔴 'secure' is not used about a deployment in the new files", not any(
    re.search(r"(?i)\bsecure\b", read(p)) for p in ("backend/deployment.py", "backend/check_deployment.py",
                                                    "backend/tools/check_pilot.py", "backend/tools/new_organisation.py")))

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
