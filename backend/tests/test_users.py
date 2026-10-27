"""
G3 (14 Oct 2026) — per-person logins: backend/users.py, the session path in access.py, the
login branch of main._check_admin and main._by, and the /api/auth/* and /api/admin/users*
endpoint bodies (FastAPI stubbed, so the bodies run as plain functions).

Run from the repo root:  python backend/tests/test_users.py

What this proves, on a scratch SQLite database with a fake clock and SMTP stubbed:
the scrypt hash and its checks; the password rule; adding a login (email shape, one per
address, a team slot or none); the Users list never carries a hash and shows a team by its
NAME; a session's cookie, its access dict (the same shape a code gives), its expiry, the
five-minute touch, sign-out, Disable and a role change ending it; a demo session never
outliving its login; sign-in with ONE refusal message for every reason, the 15-minute lock
after five failures, the IP limit; invite and reset links single-use and time-limited, the
newest one only; a demo link reusable until the login ends (D50); a password change signing
every other browser out; the last admin protected; access.resolve_request (a code first, a
session second); an admin LOGIN passing _check_admin without the token (D53) while a planner
login and the shared ADMIN_CODE do not; a login's own name in every "by" column; the audit
log (secrets removed, 4 KB cap, the actor named, page opens for demo logins only, D51); the
leads' personal login button (D56); the shared codes on only while set (D49).

What it does not prove: the HTTP layer (the cookie actually set by the browser, the
middleware's guard header and its audit row — http_smoke.py drives those through the real
app), Postgres, a real SMTP send, a browser.
"""
import datetime
import json
import os
import re
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


# --------------------------------------------------------------------------- the FastAPI stub
def _passthrough_decorator(*a, **k):
    def wrap(fn):
        return fn
    return wrap


class _App:
    def __init__(self, *a, **k):
        pass

    def get(self, *a, **k):
        return _passthrough_decorator()

    post = put = delete = patch = get

    def add_middleware(self, *a, **k):
        pass

    def mount(self, *a, **k):
        pass


class _HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Client:
    host = "203.0.113.50"


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})
        self.client = _Client()


_fa.Request = _Request
sys.modules.setdefault("fastapi", _fa)
_mw = types.ModuleType("fastapi.middleware")
_cors = types.ModuleType("fastapi.middleware.cors")
_cors.CORSMiddleware = object
_mw.cors = _cors
sys.modules.setdefault("fastapi.middleware", _mw)
sys.modules.setdefault("fastapi.middleware.cors", _cors)
_resp = types.ModuleType("fastapi.responses")
_resp.FileResponse = lambda *a, **k: None


class _Response:
    def __init__(self, content=None, status_code=200, headers=None, media_type=None, background=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type
        self.background = background
        self.set = []
        self.deleted = []

    def set_cookie(self, **kw):
        self.set.append(kw)

    def delete_cookie(self, key, **kw):
        self.deleted.append(key)


class _JSONResponse(_Response):
    pass


_resp.Response = _Response
_resp.JSONResponse = _JSONResponse
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)
_st = types.ModuleType("starlette")
_stbg = types.ModuleType("starlette.background")


class _BackgroundTask:
    def __init__(self, fn, *a, **k):
        self.fn, self.a, self.k = fn, a, k

    def run(self):
        return self.fn(*self.a, **self.k)


_stbg.BackgroundTask = _BackgroundTask
_st.background = _stbg
sys.modules.setdefault("starlette", _st)
sys.modules.setdefault("starlette.background", _stbg)

TMP = tempfile.mkdtemp(prefix="wayscope_users_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
for v in ("DATABASE_URL", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL", "APP_URL",
          "DEMO_TEAM_CODE_VAR", "DEMO_REPLY_TO", "ALLOW_DEMO_CODES", "MAP_GATE", "TENANT_ID",
          "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-for-tests", "PLANNER_CODE": "planner-secret-xyz",
                   "ADMIN_CODE": "admin-secret-xyz", "IPT1_CODE": "north-team-code",
                   "MAP_PASSWORD": "map-pass-abc", "GATE_SECRET": "gate-secret-for-tests"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import users  # noqa: E402
import access  # noqa: E402
import gate  # noqa: E402
import demo_request as dr  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def raises(fn, status=None):
    """The HTTPException status fn raises, or None."""
    try:
        fn()
    except _HTTPException as e:
        return e.status_code if status is None else e.status_code == status
    return None if status is None else False


T0 = datetime.datetime(2026, 10, 14, 9, 0, tzinfo=datetime.timezone.utc)


def at(**delta):
    users.NOW = T0 + datetime.timedelta(**delta)
    return users.NOW


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_db(); db.init_taxonomy_db(); db.init_demo_requests_db(); db.init_users_db()
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)",
               (db.current_tenant(), "IPT1", "North Team", True))
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)",
               (db.current_tenant(), "IPT2", "Central Team", True))
    at()


def as_(acc):
    """Run the next calls as this access (the middleware's contextvar)."""
    return access._ACCESS.set(acc)


def txt(msg):
    """An email's plain text, single-part or multipart."""
    return (msg.get_body(preferencelist=("plain",)) or msg).get_content()


REQ = _Request(headers={"user-agent": "UA", "x-forwarded-for": "198.51.100.77"})


def cookie_of(resp):
    for kw in getattr(resp, "set", []):
        if kw.get("key") == users.SESSION_COOKIE:
            return kw
    return None


# 27 Oct 2026 (F3 b): a staff login's session resolves only once two-step sign-in is on. These helpers turn it on
# with a fixed key (as finish_setup would), and walk the second step of a sign-in.
SECRET = "JBSWY3DPEHPK3PXP"


def on2(uid, secret=SECRET):
    db.execute("UPDATE users SET totp_secret = ?, totp_last_step = NULL WHERE id = ?", (secret, uid))


def code_for(secret=SECRET):
    return users.totp_at(secret, users.totp_step())


def step2(ans, remember=False):
    """The second step after main.auth_signin / main.auth_reset answered a ticket: the set-up step with the offered
    key, or the code step. The fake clock stands still, so the last step used is cleared first (otherwise every
    sign-in after the first in one test step would be a replayed code, refused — which section 12 asserts)."""
    if ans["step"] == "setup":
        return main.auth_setup(main.CodeIn(ticket=ans["ticket"], code=code_for(ans["key"].replace(" ", "")),
                                           remember=remember), REQ)
    u = users.find_by_email(ans["email"])
    db.execute("UPDATE users SET totp_last_step = NULL WHERE id = ?", (u["id"],))
    return main.auth_code(main.CodeIn(ticket=ans["ticket"], code=code_for(u["totp_secret"]), remember=remember), REQ)


reset_db()
GOOD_PW = "correct horse battery"

# =========================================================================== #
#  1. passwords                                                                #
# =========================================================================== #
h = users.hash_password(GOOD_PW)
ok("the hash is scrypt$n$r$p$salt$hash and holds no trace of the password",
   re.fullmatch(r"scrypt\$16384\$8\$1\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]+", h) is not None and "horse" not in h)
ok("the right password verifies, a wrong one does not", users.verify_password(GOOD_PW, h)
   and not users.verify_password(GOOD_PW + "x", h))
ok("two hashes of one password differ (a random salt each)", users.hash_password(GOOD_PW) != h)
ok("🔴 a missing, empty or malformed hash never verifies and never raises",
   not users.verify_password(GOOD_PW, None) and not users.verify_password(GOOD_PW, "")
   and not users.verify_password(GOOD_PW, "md5$abc") and not users.verify_password(GOOD_PW, "scrypt$x$y")
   and not users.verify_password("", h))
ok("a non-ASCII password hashes and verifies", users.verify_password("café crème brûlée", users.hash_password("café crème brûlée")))
ok("the rule: at least 10 characters", users.password_problem("short") is not None
   and users.password_problem("abcdefghij") is None)
ok("...at most 200", users.password_problem("a" * 201) is not None and users.password_problem("abc" * 66 + "ab") is None)
ok("...not the email", users.password_problem("ada@example.org", "Ada@Example.org") is not None)
ok("...not one of the commonest", users.password_problem("password123") is not None
   and users.password_problem("Wayscope2026") is not None and users.password_problem("aaaaaaaaaa") is not None)
ok("...and no 'one capital, one symbol' rule (three words pass)", users.password_problem("purple tractor river") is None)

# =========================================================================== #
#  2. adding a login                                                           #
# =========================================================================== #
ada, err = users.create_user(" Ada@Example.ORG ", "Ada Lovelace", "admin", created_by="adm")
ok("an admin login is added; the email is trimmed and lower-cased; no password yet",
   err is None and ada["email"] == "ada@example.org" and ada["role"] == "admin" and ada["team"] is None
   and not ada["password_hash"] and ada["kind"] == "staff" and ada["disabled"] == 0)
ok("🔴 one login per address (a second is an error, not an update)",
   users.create_user("ADA@example.org", "Someone", "planner")[1] == "There is already a login for that email address.")
ok("a bad email, an empty name, an unknown role are refused",
   users.create_user("nope", "X", "planner")[1] is not None and users.create_user("x@y.org", " ", "planner")[1] is not None
   and users.create_user("x@y.org", "X", "boss")[1] is not None)
ok("a team login needs a team; 'ipt 2', 'IPT-2' and 'IPT2' are all the slot IPT2",
   users.create_user("t@y.org", "T", "team")[1] == "Pick the team this person belongs to."
   and users.create_user("t@y.org", "T", "team", "ipt 2")[0]["team"] == "IPT2")
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1")
pat, _ = users.create_user("pat@example.org", "Pat Planner", "planner", "IPT1")
ok("a planner carries no team even when one is sent", pat["team"] is None)
pub = users.public(bob)
ok("⭐ the Users list never carries the hash, and shows the team by its NAME",
   "password_hash" not in pub and pub["team_label"] == "North Team" and pub["role_label"] == "North Team"
   and pub["has_password"] is False and pub["status"] == "invited")
ok("...a slot the tenant has not named reads '<team word> <n>', never the id",
   users.team_label("IPT5") == "Team 5")
ok("planner and admin read as words", users.public(pat)["role_label"] == "Planner" and users.public(ada)["role_label"] == "Admin")
users.set_password(ada["id"], GOOD_PW); users.set_password(bob["id"], GOOD_PW); users.set_password(pat["id"], GOOD_PW)
on2(ada["id"]); on2(bob["id"]); on2(pat["id"])
ok("set_password stores a hash and the time", users.get_user(bob["id"])["password_set_at"] == "2026-10-14T09:00:00Z"
   and users.verify_password(GOOD_PW, users.get_user(bob["id"])["password_hash"]))
ok("set_password applies the rule", users.set_password(bob["id"], "short")[1] is not None)

# =========================================================================== #
#  3. sessions                                                                 #
# =========================================================================== #
raw, ttl = users.create_session(bob["id"], ip="198.51.100.1", ua="UA test")
ok("a session is a random token and lasts 12 hours (D52)", len(raw) >= 40 and ttl == 12 * 3600)
row = db.query("SELECT * FROM user_sessions")[0]
ok("🔴 the database holds the token's hash, never the token, and the IP only hashed",
   raw not in json.dumps(row) and row["token_hash"] != raw and "198.51.100.1" not in json.dumps(row)
   and row["expires_at"] == "2026-10-14T21:00:00Z")
acc, u = users.resolve_session(raw)
ok("⭐ the session resolves to the SAME shape a team code gives, plus the person",
   acc["role"] == "ipt" and acc["ipt"] == "IPT1" and acc["label"] == "North Team" and acc["via"] == "login"
   and acc["name"] == "Bob North" and acc["email"] == "bob@example.org" and acc["user_id"] == bob["id"])
ok("...so every line filter works on it unchanged",
   access.line_visible({"ipt": "IPT1"}, acc) and not access.line_visible({"ipt": "IPT2"}, acc)
   and not access.can_approve(acc) and access.ipt_for_save("IPT2", acc) == ("IPT1", None))
pacc = users.access_for(users.get_user(pat["id"]))
ok("a planner login approves and must pick a team on save, like the planner code",
   access.can_approve(pacc) and access.ipt_for_save(None, pacc)[1] is not None and access.ipt_for_save("IPT2", pacc) == ("IPT2", None))
ok("last_sign_in_at is written", users.get_user(bob["id"])["last_sign_in_at"] == "2026-10-14T09:00:00Z")
at(minutes=2); users.resolve_session(raw)
ok("last_seen_at is NOT written on every request (2 minutes in: unchanged)",
   db.query("SELECT last_seen_at FROM user_sessions")[0]["last_seen_at"] == "2026-10-14T09:00:00Z")
at(minutes=6); users.resolve_session(raw)
ok("...but after five minutes it is", db.query("SELECT last_seen_at FROM user_sessions")[0]["last_seen_at"] == "2026-10-14T09:06:00Z")
at(hours=12, seconds=1)
ok("🔴 after 12 hours the session is dead and its row deleted",
   users.resolve_session(raw) == (None, None) and not db.query("SELECT * FROM user_sessions"))
at()
raw_r, ttl_r = users.create_session(bob["id"], remember=True)
ok("'Keep me signed in on this device' lasts 30 days (D52)", ttl_r == 30 * 86400)
ok("a junk, empty or over-long cookie resolves to nothing",
   users.resolve_session("junk") == (None, None) and users.resolve_session("") == (None, None)
   and users.resolve_session("x" * 500) == (None, None) and users.resolve_session(None) == (None, None))
users.end_session(raw_r)
ok("sign-out deletes the row: the cookie is dead wherever it was copied", users.resolve_session(raw_r) == (None, None))
r1, _ = users.create_session(bob["id"]); r2, _ = users.create_session(bob["id"])
users.update_user(bob["id"], {"disabled": True})
ok("⭐ Disable ends every session of the person at once", users.resolve_session(r1) == (None, None)
   and users.resolve_session(r2) == (None, None) and users.count_sessions(bob["id"]) == 0)
users.update_user(bob["id"], {"disabled": False})
r1, _ = users.create_session(bob["id"])
users.update_user(bob["id"], {"team": "IPT2"})
ok("a change of team ends the sessions (they sign in again with the new rights)", users.resolve_session(r1) == (None, None)
   and users.access_for(users.get_user(bob["id"]))["label"] == "Central Team")
users.update_user(bob["id"], {"team": "IPT1"})
r1, _ = users.create_session(bob["id"])
users.update_user(bob["id"], {"name": "Bob N. North"})
ok("a change of name alone keeps the session, and the session reads the new name",
   users.resolve_session(r1)[0]["name"] == "Bob N. North")
ok("cookie_kwargs: HttpOnly, Secure, SameSite=Lax, path /, the session's max-age",
   users.cookie_kwargs("t", 43200) == {"key": "wayscope_session", "value": "t", "max_age": 43200, "path": "/",
                                       "httponly": True, "samesite": "lax", "secure": True})

# =========================================================================== #
#  4. sign-in and the rate limit                                               #
# =========================================================================== #
user, e_, st = users.sign_in("BOB@example.org ", GOOD_PW, ip="198.51.100.2")
ok("sign-in by email and password, any case, trimmed", user and user["id"] == bob["id"] and st == 200)
msgs = {users.sign_in("bob@example.org", "wrong password!", ip="198.51.100.3")[1],
        users.sign_in("nobody@example.org", GOOD_PW, ip="198.51.100.3")[1],
        users.sign_in("not an email", GOOD_PW, ip="198.51.100.3")[1]}
users.update_user(pat["id"], {"disabled": True})
msgs.add(users.sign_in("pat@example.org", GOOD_PW, ip="198.51.100.3")[1])
users.update_user(pat["id"], {"disabled": False})
ok("⭐ ONE refusal for a wrong password, an unknown address, a non-address and a disabled login (no enumeration)",
   msgs == {users.SIGNIN_REFUSED})
ok("...the refusal says nothing about which", users.SIGNIN_REFUSED == "That email and password don't match.")
reset_db()
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin"); users.set_password(ada["id"], GOOD_PW)
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1"); users.set_password(bob["id"], GOOD_PW)
for i in range(users.SIGNIN_FAILS_PER_EMAIL):
    users.sign_in("bob@example.org", "wrong password!", ip=f"198.51.100.{10 + i}")
_u, e_, st = users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.99")
ok("🔴 after five failures for one address in 15 minutes, even the RIGHT password is refused, 429",
   _u is None and st == 429 and e_ == users.SIGNIN_LOCKED)
ok("...another address is not affected", users.sign_in("ada@example.org", GOOD_PW, ip="198.51.100.99")[2] == 200)
at(minutes=15, seconds=1)
ok("...and 15 minutes later the address can sign in again", users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.99")[2] == 200)
reset_db()
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1"); users.set_password(bob["id"], GOOD_PW)
for i in range(4):
    users.sign_in("bob@example.org", "wrong password!", ip="198.51.100.7")
users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.7")
ok("a success does not count towards the lock (four failures + a success: still open)",
   users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.7")[2] == 200)
reset_db()
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1"); users.set_password(bob["id"], GOOD_PW)
for i in range(users.SIGNIN_TRIES_PER_IP):
    users.sign_in(f"guess{i}@example.org", "whatever pass", ip="198.51.100.8")
ok("🔴 30 tries from one IP in 15 minutes lock that IP, for any address",
   users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.8")[2] == 429
   and users.sign_in("bob@example.org", GOOD_PW, ip="198.51.100.9")[2] == 200)
ok("the attempts store hashed keys only", "bob@example.org" not in json.dumps(db.query("SELECT * FROM auth_attempts"))
   and "198.51.100.8" not in json.dumps(db.query("SELECT * FROM auth_attempts")))
at(days=1, minutes=1); users.record_attempt("x", "k", True)
ok("rows older than a day are cleared on the next write", db.query("SELECT COUNT(*) AS n FROM auth_attempts")[0]["n"] == 1)
at()
ok("the audit log names refused and locked sign-ins without the password",
   {r["kind"] for r in users.audit_rows()} >= {"signin", "signin-refused", "signin-locked"}
   and GOOD_PW not in json.dumps(users.audit_rows()) and "whatever pass" not in json.dumps(users.audit_rows()))

# =========================================================================== #
#  5. links: invite, reset, demo                                               #
# =========================================================================== #
reset_db()
cy, _ = users.create_user("cy@example.org", "Cy New", "planner")
inv = users.issue_token(cy["id"], "invite")
ok("an invite link is a fragment on APP_URL (default the demo's address)",
   users.link("invite", inv) == "https://app.wayscope.co.uk/#invite=" + inv)
os.environ["APP_URL"] = "https://app.example.test/"
ok("...APP_URL moves it (trailing slash dropped)", users.link("reset", "t") == "https://app.example.test/#reset=t")
os.environ.pop("APP_URL")
ok("peek reads an invite without using it", users.peek_token(inv, ("invite", "reset"))[1]["id"] == cy["id"]
   and users.peek_token(inv, ("invite", "reset"))[1]["id"] == cy["id"])
ok("🔴 an invite cannot be used as a demo link", users.use_token(inv, ("demo",)) == (None, None))
t_, u_ = users.use_token(inv, ("invite", "reset"))
ok("an invite works once", t_ and u_["id"] == cy["id"] and users.use_token(inv, ("invite", "reset")) == (None, None))
ok("🔴 the token is stored hashed", inv not in json.dumps(db.query("SELECT * FROM auth_tokens")))
rs1 = users.issue_token(cy["id"], "reset")
rs2 = users.issue_token(cy["id"], "reset")
ok("a new reset link retires the older unused one (only the newest works)",
   users.peek_token(rs1, ("reset",)) == (None, None) and users.peek_token(rs2, ("reset",))[0] is not None)
at(minutes=60, seconds=1)
ok("🔴 a reset link is dead after 60 minutes", users.use_token(rs2, ("reset",)) == (None, None))
at()
inv2 = users.issue_token(cy["id"], "invite")
at(hours=71)
ok("an invite lives 72 hours", users.peek_token(inv2, ("invite",))[0] is not None)
at(hours=72, seconds=1)
ok("...and not longer", users.peek_token(inv2, ("invite",)) == (None, None))
at()
inv3 = users.issue_token(cy["id"], "invite")
users.update_user(cy["id"], {"disabled": True})
ok("🔴 a disabled login's links do nothing", users.peek_token(inv3, ("invite",)) == (None, None))
users.update_user(cy["id"], {"disabled": False})
# demo links (HU14, D50)
got = users.demo_login("Lead@Example.org", "Lea Lead", "req1")
lead = got["user"]
ok("⭐ a lead's login: kind demo, their team slot, 14 days, linked to the request",
   got["status"] == "new" and lead["kind"] == "demo" and lead["role"] == "team" and lead["team"] == "IPT1"
   and lead["expires_at"] == "2026-10-28T09:00:00Z" and lead["demo_request_id"] == "req1"
   and got["link"].startswith("https://app.wayscope.co.uk/#demo="))
draw = got["link"].split("#demo=", 1)[1]
for i in range(3):
    users.use_token(draw, ("demo",))
ok("⭐ a demo link keeps working until the login ends, each use counted (D50)",
   users.peek_token(draw, ("demo",))[0]["uses"] == 3)
ok("🔴 a demo link cannot set a password", users.peek_token(draw, ("invite", "reset")) == (None, None))
s_d, ttl_d = users.create_session(lead["id"], remember=True)
ok("a demo session never outlives its login (30 days asked, 14 days given)", ttl_d == 14 * 86400)
at(days=14, seconds=1)
ok("🔴 when the login ends, its link and its session end with it",
   users.peek_token(draw, ("demo",)) == (None, None) and users.resolve_session(s_d) == (None, None)
   and users.sign_in("lead@example.org", "anything at all")[1] == users.SIGNIN_REFUSED)
ok("an expired demo login reads 'expired' on the list", users.public(users.get_user(lead["id"]))["status"] == "expired")
again = users.demo_login("lead@example.org", "Lea Lead", "req2")
ok("asking again renews the SAME login for 14 days from now, with a new link",
   again["status"] == "renewed" and again["user"]["id"] == lead["id"] and again["user"]["expires_at"] == "2026-11-11T09:00:01Z"
   and users.peek_token(again["link"].split("#demo=", 1)[1], ("demo",))[0] is not None)
at()
ok("a staff address gets no demo login", users.demo_login("cy@example.org", "Cy", "req3")["status"] == "staff"
   and users.get_user(cy["id"])["kind"] == "staff")
ok("nice_date reads 'Wed 28 Oct 2026'", users.nice_date("2026-10-28T09:00:00Z") == "Wed 28 Oct 2026")
pd = users.demo_login("convert@example.org", "Con Vert")
pdraw = pd["link"].split("#demo=", 1)[1]
s_pd, _ = users.create_session(pd["user"]["id"])
pu, perr = users.promote_demo(pd["user"]["id"], "Con Vert", "planner")
ok("⭐ a lead who becomes a customer: promote_demo makes the demo login a staff planner with no end date",
   perr is None and pu["kind"] == "staff" and pu["expires_at"] is None and pu["role"] == "planner")
ok("🔴 ...their personal link and their sessions end", users.peek_token(pdraw, ("demo",)) == (None, None)
   and users.resolve_session(s_pd) == (None, None))
ok("promote_demo refuses a staff login", users.promote_demo(cy["id"], "Cy", "planner")[1] is not None)

# =========================================================================== #
#  6. changing logins: the last admin, yourself                                #
# =========================================================================== #
reset_db()
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin")
ok("🔴 the last admin cannot be disabled or made a planner",
   users.update_user(ada["id"], {"disabled": True})[1] and users.update_user(ada["id"], {"role": "planner"})[1]
   and users.get_user(ada["id"])["role"] == "admin")
eve, _ = users.create_user("eve@example.org", "Eve Admin", "admin")
ok("...with a second admin, it can", users.update_user(ada["id"], {"role": "planner"})[1] is None)
users.update_user(ada["id"], {"role": "admin"})
ok("🔴 nobody can disable their own login", users.update_user(ada["id"], {"disabled": True}, by_user_id=ada["id"])[1]
   == "You can't disable your own login.")
ok("an unknown id is 'No such login.'", users.update_user("nope", {"name": "x"})[1] == "No such login.")
ok("an expiry must be the ISO form", users.update_user(eve["id"], {"expires_at": "tomorrow"})[1] is not None)

# =========================================================================== #
#  7. access.resolve_request: a code first, a session second                   #
# =========================================================================== #
reset_db()
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1")
on2(bob["id"])
s_b, _ = users.create_session(bob["id"])
ok("a session alone resolves to the login", access.resolve_request(None, s_b)["via"] == "login")
ok("a valid code wins over a session cookie left in the same browser",
   access.resolve_request("planner-secret-xyz", s_b)["role"] == "planner"
   and access.resolve_request("planner-secret-xyz", s_b)["via"] == "code")
ok("a code that no longer resolves falls back to the session", access.resolve_request("stale-code", s_b)["via"] == "login")
ok("nothing → None", access.resolve_request(None, None) is None and access.resolve_request("", "junk") is None)
ok("D49: while a code is set, users.codes_enabled() is True", users.codes_enabled() is True)
_saved = {k: os.environ.pop(k) for k in ("PLANNER_CODE", "ADMIN_CODE", "IPT1_CODE")}
ok("⭐ D49: with the eight variables deleted, no code resolves and logins still do",
   users.codes_enabled() is False and access.resolve_request("planner-secret-xyz", None) is None
   and access.resolve_request("planner-secret-xyz", s_b)["via"] == "login")
os.environ.update(_saved)
d = access.describe(access.resolve_request(None, s_b))
ok("describe() of a login: via login, the person's name and email, the team NAME, whether codes are on",
   d["via"] == "login" and d["name"] == "Bob North" and d["email"] == "bob@example.org" and d["label"] == "North Team"
   and d["codes"] is True and d["ipt_locked"] is True and d["kind"] == "staff")
d2 = access.describe(access.resolve("planner-secret-xyz"))
ok("describe() of a code: via code, no name or email", d2["via"] == "code" and "email" not in d2 and "name" not in d2)
ok("⭐ the gate opens /map/, /help/, /bulletin/ to a session (has_valid_code covers it)",
   all(gate.decide(p, has_valid_code=bool(access.resolve_request(None, s_b))) == gate.ALLOW
       for p in ("/map/", "/help/", "/bulletin/", "/api/routes/R1/geometry")))

# =========================================================================== #
#  8. main._check_admin and main._by                                           #
# =========================================================================== #
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin")
pat, _ = users.create_user("pat@example.org", "Pat Planner", "planner")
tok = as_(users.access_for(users.get_user(ada["id"])))
ok("⭐ D53: an admin LOGIN passes _check_admin with no token", raises(lambda: main._check_admin(None)) is None)
ok("_by(): a login's own name wins over what the browser sent", main._by("Mallory") == "Ada Lovelace")
access._ACCESS.reset(tok)
tok = as_(users.access_for(users.get_user(pat["id"])))
ok("🔴 a planner login does not", raises(lambda: main._check_admin(None)) == 403)
access._ACCESS.reset(tok)
tok = as_(access.resolve_request("admin-secret-xyz"))
ok("🔴 the shared ADMIN_CODE still does not (the boundary is unchanged)", raises(lambda: main._check_admin(None)) == 403)
ok("_by(): on a code the typed name is all there is", main._by("Typed Name") == "Typed Name")
access._ACCESS.reset(tok)
ok("the admin token still works for scripts", raises(lambda: main._check_admin("adm-token-for-tests")) is None)
ok("...and nobody signed in with no token is refused", raises(lambda: main._check_admin(None)) == 403)
MAIN = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("every 'by' the server records goes through _by() (16 sites)", MAIN.count("by=_by(") >= 15
   and "_by(row.submitted_by)" in MAIN and not re.search(r"by=body\.\w+[,)]", MAIN))

# =========================================================================== #
#  9. the audit trail                                                          #
# =========================================================================== #
reset_db()
ok("scrub removes every secret key, nested, and keeps the rest",
   users.scrub({"password": "p", "new_password": "p", "token": "t", "code": "c", "admin_token": "t",
                "nested": {"secret": "s", "mapPassword": "m"}, "list": [{"access_code": "c"}], "qty": 5,
                "submitted_by": "Ada"})
   == {"password": "(removed)", "new_password": "(removed)", "token": "(removed)", "code": "(removed)",
       "admin_token": "(removed)", "nested": {"secret": "(removed)", "mapPassword": "(removed)"},
       "list": [{"access_code": "(removed)"}], "qty": 5, "submitted_by": "Ada"})
big = {"rows": [{"q": i} for i in range(2000)]}
users.audit("write", acc=None, method="POST", path="/api/forecasts/bulk", status=200, detail=big)
r_ = users.audit_rows()[0]
ok("a big body is capped at 4 KB", len(r_["detail"]) <= users.AUDIT_DETAIL_MAX and r_["detail"].endswith("…"))
users.audit("write", acc=None, path="/api/first"); users.audit("write", acc=None, path="/api/second")
ok("rows written in the same second list newest first (time-ordered ids)",
   [r["path"] for r in users.audit_rows(kind="write")][:2] == ["/api/second", "/api/first"])
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin")
users.audit("write", acc=users.access_for(ada), method="PUT", path="/api/admin/config/factors", status=200,
            detail={"body": {"doc": {"x": 1}, "updated_by": "Ada"}, "query": {"token": "adm-token-for-tests"}})
r_ = users.audit_rows(actor_id=ada["id"])[0]
ok("⭐ a login's write names the person, the path and the body, and never the token",
   r_["actor_kind"] == "user" and r_["actor_label"] == "Ada Lovelace <ada@example.org>" and r_["path"] == "/api/admin/config/factors"
   and '"doc":{"x":1}' in r_["detail"] and "adm-token-for-tests" not in r_["detail"])
users.audit("write", acc=access.resolve("planner-secret-xyz"), method="PUT", path="/api/x", status=200)
users.audit("write", acc=None, token_used=True, method="POST", path="/api/admin/y", status=200)
labels = [r["actor_label"] for r in users.audit_rows(kind="write")]
ok("a shared code is named as a code, the admin token as the token",
   "Planner code (shared)" in labels and "admin token" in labels)
ok("...and a code holder who typed the admin token is named as both",
   users.actor_of(access.resolve("planner-secret-xyz"), token_used=True)[2] == "Planner code (shared), with the admin token")
lead = users.demo_login("lead@example.org", "Lea Lead")["user"]
ok("⭐ D51: a page open is recorded for a DEMO login", users.record_page(users.access_for(lead), "Look-ahead!") is True
   and users.audit_rows(kind="page")[0]["target"] == "look-ahead")
ok("🔴 ...and NOT for a staff login, a code or nobody",
   users.record_page(users.access_for(ada), "dashboard") is False
   and users.record_page(access.resolve("planner-secret-xyz"), "dashboard") is False
   and users.record_page(None, "dashboard") is False and len(users.audit_rows(kind="page")) == 1)
ok("an empty page word is not recorded", users.record_page(users.access_for(lead), "!!!") is False)
csv_ = users.audit_csv()
ok("the activity CSV: a header and one line per row", csv_.split("\n")[0] == ",".join(users.AUDIT_CSV_COLUMNS)
   and len(csv_.strip().split("\n")) == 1 + len(users.audit_rows(limit=5000)))
_real_exec = db.execute
db.execute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full"))
try:
    users.audit("write", acc=None, path="/api/x")
    ok("🔴 a failed audit write never raises into the request", True)
except Exception:
    ok("🔴 a failed audit write never raises into the request", False)
finally:
    db.execute = _real_exec

# =========================================================================== #
# 10. the endpoint bodies (FastAPI stubbed)                                    #
# =========================================================================== #
reset_db()
SENT = []
dr.send = lambda msg, settings: SENT.append(msg)
ok("with no session nobody is signed in", main.auth_me()["signed_in"] is False and main.auth_me()["codes"] is True)
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin")
users.set_password(ada["id"], GOOD_PW)
a0 = main.auth_signin(main.SignInIn(email="ada@example.org", password=GOOD_PW), REQ)
ok("⭐ F3 b: a staff sign-in's password step answers the set-up step and NO session cookie",
   isinstance(a0, dict) and a0["step"] == "setup" and a0["ticket"] and "<svg" in a0["qr"]
   and len(a0["key"].replace(" ", "")) == 32 and not db.query("SELECT * FROM user_sessions"))
r_ = step2(a0)
ck = cookie_of(r_)
ok("⭐ /api/auth/signin answers what the person can do and sets the session cookie (HttpOnly, Secure, Lax, 12 h)",
   r_.body["role"] == "admin" and r_.body["name"] == "Ada Lovelace" and r_.body["via"] == "login"
   and ck and ck["httponly"] and ck["secure"] and ck["samesite"] == "lax" and ck["max_age"] == 43200)
r_ = step2(main.auth_signin(main.SignInIn(email="ada@example.org", password=GOOD_PW, remember=True), REQ), remember=True)
ok("...30 days with remember", cookie_of(r_)["max_age"] == 30 * 86400)
ok("a wrong password is a 401 with the one message",
   raises(lambda: main.auth_signin(main.SignInIn(email="ada@example.org", password="nope nope nope"), REQ)) == 401)
admin_raw = ck["value"]
tok = as_(access.resolve_request(None, admin_raw))
ok("/api/auth/me reads the session", main.auth_me()["access"]["email"] == "ada@example.org")
# Users: add (no SMTP → the link comes back), change, reset
add = main.admin_user_add(main.UserIn(email="bob@example.org", name="Bob North", role="team", team="IPT1"))
ok("⭐ Users → Add (no sender): the login is made and the invite link comes back for the admin to pass on",
   add["user"]["email"] == "bob@example.org" and add["email"] == "unsent" and add["purpose"] == "invite"
   and add["link"].startswith("https://app.wayscope.co.uk/#invite="))
ok("...created_by names the admin", users.find_by_email("bob@example.org")["created_by"] == "Ada Lovelace <ada@example.org>")
lst = main.admin_users(None)
ok("Users list: every login, teams by NAME, codes on, no mail, me = the admin",
   {u["email"] for u in lst["users"]} == {"ada@example.org", "bob@example.org"}
   and {"id": "IPT1", "label": "North Team"} in lst["teams"] and lst["codes"] is True and lst["mail"] is False
   and lst["me"] == ada["id"] and "password_hash" not in json.dumps(lst))
ok("a duplicate address is a 400", raises(lambda: main.admin_user_add(main.UserIn(email="BOB@example.org", name="B", role="planner"))) == 400)
bob_id = add["user"]["id"]
ch = main.admin_user_change(bob_id, main.UserPatch(role="planner"))
ok("change role to Planner drops the team", ch["user"]["role"] == "planner" and ch["user"]["team"] is None)
ok("🔴 the admin cannot disable themself through the endpoint", raises(lambda: main.admin_user_change(ada["id"], main.UserPatch(disabled=True))) == 400)
ok("an unknown login is a 404", raises(lambda: main.admin_user_change("nope", main.UserPatch(name="x"))) == 404)
os.environ.update({"SMTP_USER": "s@wayscope.co.uk", "SMTP_PASSWORD": "pw", "DEMO_FROM": "Wayscope <s@wayscope.co.uk>",
                   "DEMO_NOTIFY": "n@wayscope.co.uk"})
SENT.clear()
rs = main.admin_user_reset(bob_id)
ok("⭐ Send reset (with a sender): the invite is emailed and the link is NOT returned",
   rs["email"] == "sent" and "link" not in rs and len(SENT) == 1 and SENT[0]["To"] == "bob@example.org"
   and SENT[0]["From"] == "Wayscope <s@wayscope.co.uk>"   # DEMO_FROM as Render has it, not wrapped a second time
   and "#invite=" in SENT[0].get_content() and SENT[0]["Subject"] == "Your Wayscope sign-in")
inv_link = re.search(r"https://\S+#invite=\S+", SENT[0].get_content()).group(0)
access._ACCESS.reset(tok)
# the invitee sets a password
itok = inv_link.split("#invite=", 1)[1]
ok("/api/auth/check greets the invitee without using the link",
   main.auth_check(main.TokenIn(token=itok)) == {"purpose": "invite", "name": "Bob North", "email": "bob@example.org"}
   and users.peek_token(itok, ("invite",))[0] is not None)
ok("a too-short password is a 400 and does NOT burn the link",
   raises(lambda: main.auth_reset(main.ResetIn(token=itok, password="short"), REQ)) == 400
   and users.peek_token(itok, ("invite",))[0] is not None)
r0 = main.auth_reset(main.ResetIn(token=itok, password=GOOD_PW), REQ)
ok("⭐ F3 b: the invite's password goes on to the set-up step, not straight to a session",
   isinstance(r0, dict) and r0["step"] == "setup" and r0["email"] == "bob@example.org")
r_ = step2(r0)
ok("⭐ setting the password from the invite signs the person in", r_.body["email"] == "bob@example.org" and cookie_of(r_))
ok("...and the link is used up (410 the second time)", raises(lambda: main.auth_reset(main.ResetIn(token=itok, password=GOOD_PW), REQ)) == 410
   and raises(lambda: main.auth_check(main.TokenIn(token=itok))) == 410)
bob_raw = cookie_of(r_)["value"]
# forgot → reset
SENT.clear()
fr = main.auth_forgot(main.EmailIn(email="bob@example.org"), REQ)
ok("/api/auth/forgot answers the same words and sends in the background",
   fr.body["message"].startswith("If that address has a Wayscope login") and fr.background is not None and not SENT)
fr.background.run()
ok("...the background sends a RESET link (Bob has a password now)", len(SENT) == 1 and "#reset=" in SENT[0].get_content()
   and SENT[0]["Subject"] == "Reset your Wayscope password" and "60 minutes" in SENT[0].get_content())
fr2 = main.auth_forgot(main.EmailIn(email="nobody@example.org"), REQ)
SENT.clear(); fr2.background.run()
ok("🔴 an unknown address: the same answer, and nothing is sent", fr2.body == fr.body and not SENT)
ok("a non-address gets the same answer with no background at all",
   main.auth_forgot(main.EmailIn(email="nonsense"), REQ) == fr.body)
main.auth_forgot(main.EmailIn(email="bob@example.org"), REQ); main.auth_forgot(main.EmailIn(email="bob@example.org"), REQ)
ok("🔴 three reset requests for one address in an hour, then 429",
   raises(lambda: main.auth_forgot(main.EmailIn(email="bob@example.org"), REQ)) == 429)
rtok = users.issue_token(bob_id, "reset")
other_raw, _ = users.create_session(bob_id)
r0 = main.auth_reset(main.ResetIn(token=rtok, password="a brand new password"), REQ)
ok("🔴 F3 b: a reset link never skips the code (the code step, no cookie)", isinstance(r0, dict) and r0["step"] == "code")
r_ = step2(r0)
ok("⭐ a reset signs every OTHER browser out and this one in",
   users.resolve_session(other_raw) == (None, None) and users.resolve_session(bob_raw) == (None, None)
   and users.resolve_session(cookie_of(r_)["value"])[0]["email"] == "bob@example.org")
bob_raw = cookie_of(r_)["value"]
# change your own password
tok = as_(access.resolve_request(None, bob_raw))
ok("a wrong current password is a 400",
   raises(lambda: main.auth_password(main.PasswordIn(current="not it at all", new="another good password"), REQ)) == 400)
r_ = main.auth_password(main.PasswordIn(current="a brand new password", new="another good password"), REQ)
ok("changing your password works and keeps you signed in on a fresh session",
   users.verify_password("another good password", users.get_user(bob_id)["password_hash"]) and cookie_of(r_))
access._ACCESS.reset(tok)
ok("/api/auth/password with no login is a 401",
   raises(lambda: main.auth_password(main.PasswordIn(current="x", new="y"), REQ)) == 401)
# sign out
sraw = cookie_of(r_)["value"]
tok = as_(access.resolve_request(None, sraw))
so = main.auth_signout(_Request(cookies={users.SESSION_COOKIE: sraw}))
access._ACCESS.reset(tok)
mapck = [k for k in so.set if k["key"] == gate.COOKIE]
ok("⭐ sign out deletes the session row, drops its cookie, and leaves a MAP cookie on this machine",
   users.resolve_session(sraw) == (None, None) and users.SESSION_COOKIE in so.deleted
   and mapck and gate.verify(mapck[0]["value"]) == gate.LEVEL_MAP and mapck[0]["max_age"] <= 43200)
ok("🔴 ...never a staff cookie", not any(gate.verify(k["value"]) == gate.LEVEL_STAFF for k in so.set))
ok("...and the sign-out is in the audit log", any(r["kind"] == "signout" for r in users.audit_rows()))
# the demo link endpoint
got = users.demo_login("lead@example.org", "Lea Lead", "req9")
dl = got["link"].split("#demo=", 1)[1]
r_ = main.auth_link(main.TokenIn(token=dl), REQ)
ok("⭐ /api/auth/link signs a lead in on their personal link", r_.body["kind"] == "demo" and r_.body["label"] == "North Team"
   and cookie_of(r_)["max_age"] == 14 * 86400)
ok("...again and again (D50)", main.auth_link(main.TokenIn(token=dl), REQ).body["kind"] == "demo")
ok("a junk link is a 410", raises(lambda: main.auth_link(main.TokenIn(token="junk"), REQ)) == 410)
tok = as_(access.resolve_request(None, cookie_of(r_)["value"]))
ok("D51: the lead's page open is recorded through /api/activity", main.activity(main.ActivityIn(page="map"))["recorded"] is True)
ok("🔴 the lead cannot reach Users", raises(lambda: main.admin_users(None)) == 403)
access._ACCESS.reset(tok)
# D56: a lead from before 14 Oct gets a personal login on request
rid = dr.store({"name": "Old Lead", "email": "old@example.org", "organisation": "O", "role": "Other", "wants": "",
                "updates_opt_in": False}, "h", "sent")
tok = as_(access.resolve_request(None, admin_raw))
SENT.clear()
ll = main.admin_lead_login(rid)
ok("⭐ D56: 'Send a personal login' makes the old lead's login and emails the link — one lead, one email",
   ll["status"] == "new" and ll["email"] == "sent" and len(SENT) == 1 and SENT[0]["To"] == "old@example.org"
   and "#demo=" in txt(SENT[0]) and "north-team-code" not in txt(SENT[0]))
ok("...the lead list shows the login", [x for x in main.admin_leads(None)["leads"] if x["email"] == "old@example.org"][0]["login"] == "active")
ok("...a staff address is refused", raises(lambda: main.admin_lead_login(dr.store(
    {"name": "Ada", "email": "ada@example.org", "organisation": "O", "role": "Other", "wants": "", "updates_opt_in": False},
    "h", "sent"))) == 400)
ext = main.admin_user_change(ll["user"]["id"], main.UserPatch(extend_days=7))
ok("Extend gives a demo login 7 more days", ext["user"]["expires_at"] == "2026-11-04T09:00:00Z")
ok("🔴 ...a staff login has no end date to extend", raises(lambda: main.admin_user_change(bob_id, main.UserPatch(extend_days=7))) == 400)
ok("the activity endpoints answer rows and a CSV", len(main.admin_audit(None)["rows"]) > 0
   and main.admin_audit_csv(None).media_type == "text/csv")
access._ACCESS.reset(tok)
for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
    os.environ.pop(k)
ok("🔴 nobody signed in cannot reach any Users endpoint without the token",
   all(raises(fn) == 403 for fn in (lambda: main.admin_users(None), lambda: main.admin_leads(None),
                                    lambda: main.admin_audit(None), lambda: main.admin_user_reset(bob_id))))
ok("...with the token (the first admin, D47) they work", "users" in main.admin_users("adm-token-for-tests"))

# =========================================================================== #
# 11. wiring, by source                                                        #
# =========================================================================== #
ok("the lifespan creates the login tables after the demo requests and before init_tenant()",
   0 < MAIN.find("db.init_demo_requests_db()") < MAIN.find("db.init_users_db()") < MAIN.find("db.init_tenant()"))
ok("⭐ the middleware reads the session cookie into the request's access",
   "access.set_current(request.headers.get(access.HEADER),\n                                   request.cookies.get(users.SESSION_COOKIE))" in MAIN)
ok("⭐ a cookie-authenticated write without the app's header is refused (and every /api/auth/ POST needs it)",
   'GUARD_HEADER = "X-Wayscope"' in MAIN
   and re.search(r'if write and request\.headers\.get\(GUARD_HEADER\) != "1" and \(\n\s+\(acc_now and acc_now\.get\("via"\) == "login"\) or path\.startswith\("/api/auth/"\)\):', MAIN))
ok("⭐ the middleware writes one audit row per write that worked",
   re.search(r"if write and _audited\(path\) and 200 <= getattr\(response, \"status_code\", 0\) < 300:\n\s+_audit_write\(", MAIN))
ok("...skipping only the POSTs that change nothing and the paths that log themselves",
   set(main.AUDIT_SKIP) == {"/api/costing/preview", "/api/carbon/scenario", "/api/carbon/summary.pdf",
                            "/api/public/demo-request", "/api/map-auth", "/api/gate-signout", "/api/auth", "/api/activity"}
   and main._audited("/api/forecasts/bulk") and main._audited("/api/admin/config/factors")
   and main._audited("/api/routes/R1/status") and not main._audited("/api/auth/signin"))
ok("🔴 CORS no longer allows every origin with credentials",
   'allow_origins=["*"]' not in MAIN and "allow_origins=[], allow_credentials=False" in MAIN)
ok("🔴 the reset link's address comes from APP_URL, never the request's Host header (app_url reads nothing else)",
   set(users.app_url.__code__.co_names) <= {"os", "getenv", "strip", "rstrip", "DEFAULT_APP_URL"}
   and 'os.getenv("APP_URL")' in open(os.path.join(BACKEND, "users.py"), encoding="utf-8").read())
ok("the login tables are not package data (an import cannot delete them)",
   not ({"users", "user_sessions", "auth_tokens", "audit_log", "auth_attempts"} & set(db.TENANTED_TABLES)))
ok("every login table query filters on the tenant",
   all("tenant_id = ?" in q or "tenant_id," in q or "(tenant_id" in q
       for q in re.findall(r'"((?:SELECT|UPDATE|DELETE|INSERT)[^"]*(?:users|user_sessions|auth_tokens|audit_log|auth_attempts)[^"]*)"',
                           open(os.path.join(BACKEND, "users.py"), encoding="utf-8").read())))
for fn in ("render.yaml", "env.example"):
    txt = open(os.path.join(ROOT, fn), encoding="utf-8").read()
    ok(f"{fn} documents APP_URL", "APP_URL" in txt)

# =========================================================================== #
# 12. two-step sign-in (27 Oct 2026, pilot readiness F3 b)                     #
# =========================================================================== #
import base64 as _b64  # noqa: E402
_rfc = _b64.b32encode(b"12345678901234567890").decode()
ok("⭐ TOTP matches RFC 6238's SHA-1 test vectors (6 digits)",
   [users.totp_at(_rfc, t // 30) for t in (59, 1111111109, 1111111111, 1234567890, 2000000000)]
   == ["287082", "081804", "050471", "005924", "279037"])
reset_db()
ada, _ = users.create_user("ada@example.org", "Ada Lovelace", "admin"); users.set_password(ada["id"], GOOD_PW)
bob, _ = users.create_user("bob@example.org", "Bob North", "team", "IPT1"); users.set_password(bob["id"], GOOD_PW)
s_old, _ = users.create_session(bob["id"])
ok("🔴 a staff session from before two-step does not resolve (they sign in again and set it up)",
   users.resolve_session(s_old) == (None, None))
lead = users.demo_login("lead@example.org", "Lea Lead")["user"]
s_lead, _ = users.create_session(lead["id"])
ok("...a lead's demo login needs none (a fictional scheme)", users.needs_two_step(lead) is False
   and users.resolve_session(s_lead)[0]["kind"] == "demo")
ok("every staff role needs it: admin, planner, team",
   all(users.needs_two_step(u) for u in (users.get_user(ada["id"]), users.get_user(bob["id"]))))
a0 = main.auth_signin(main.SignInIn(email="bob@example.org", password=GOOD_PW), REQ)
key = a0["key"].replace(" ", "")
ok("the set-up answer: a fresh 32-character key, shown in groups of four, and a QR code drawn here",
   a0["step"] == "setup" and re.fullmatch(r"[A-Z2-7]{32}", key) and a0["key"].count(" ") == 7
   and a0["qr"].startswith("<svg") and "http" not in a0["qr"].replace("http://www.w3.org/2000/svg", ""))
ok("...the key waits as 'pending', not on, until a code confirms it",
   users.get_user(bob["id"])["totp_pending"] == key and not users.get_user(bob["id"])["totp_secret"])
ok("the authenticator link names Wayscope and the address",
   users.otpauth_uri(key, "bob@example.org") == f"otpauth://totp/Wayscope%3Abob%40example.org?secret={key}&issuer=Wayscope&digits=6&period=30")
ok("🔴 a wrong set-up code: 401, two-step still off, the ticket still live",
   raises(lambda: main.auth_setup(main.CodeIn(ticket=a0["ticket"], code="000000"), REQ)) == 401
   and not users.two_step_on(users.get_user(bob["id"])) and users.peek_token(a0["ticket"], ("mfa",))[0] is not None)
su = main.auth_setup(main.CodeIn(ticket=a0["ticket"], code=code_for(key)), REQ)
codes = su.body["recovery_codes"]
ok("⭐ the right code turns it on, signs in, and shows ten recovery codes once",
   cookie_of(su) and users.two_step_on(users.get_user(bob["id"])) and len(codes) == 10 and len(set(codes)) == 10
   and all(re.fullmatch(r"[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", c) for c in codes)
   and su.body["two_step"] is True and su.body["recovery_left"] == 10)
bu = users.get_user(bob["id"])
ok("🔴 the codes are stored hashed only; the pending key is cleared",
   not any(c in (bu["recovery_hashes"] or "") or c.replace("-", "") in (bu["recovery_hashes"] or "") for c in codes)
   and bu["totp_pending"] is None and bu["totp_secret"] == key)
ok("...the ticket is used up", raises(lambda: main.auth_setup(main.CodeIn(ticket=a0["ticket"], code=code_for(key)), REQ)) == 410)
ok("the set-up is in the activity log", any(r["kind"] == "two-step-on" for r in users.audit_rows()))
ok("🔴 the Users list never carries the key, the pending key or the code hashes",
   all(k not in json.dumps(users.public(bu)) for k in (key, "recovery_hashes", "totp_secret", "totp_pending"))
   and users.public(bu)["two_step"] is True)
# the code step
t1 = main.auth_signin(main.SignInIn(email="bob@example.org", password=GOOD_PW), REQ)
ok("⭐ with two-step on, the password step answers the code step (no key, no QR, no cookie)",
   t1["step"] == "code" and "key" not in t1 and "qr" not in t1)
ok("🔴 the code just used at set-up is refused (a code works once)",
   raises(lambda: main.auth_code(main.CodeIn(ticket=t1["ticket"], code=code_for(key)), REQ)) == 401)
at(seconds=30)
ok("...the next step's code works", cookie_of(main.auth_code(main.CodeIn(ticket=t1["ticket"], code=code_for(key)), REQ)))
ok("🔴 the code-step ticket is single use", raises(lambda: main.auth_code(main.CodeIn(ticket=t1["ticket"], code=code_for(key)), REQ)) == 410)
at(seconds=120)
t2 = users.start_two_step(users.get_user(bob["id"]))
prev = users.totp_at(key, users.totp_step() - 1)
nxt2 = users.totp_at(key, users.totp_step() + 2)
ok("a phone clock one step behind still works; two steps out does not",
   users.totp_match(key, prev) == users.totp_step() - 1 and users.totp_match(key, nxt2) is None)
ok("codes with spaces are read; letters, 5 or 7 digits are not",
   users.totp_match(key, " ".join(code_for(key))) is not None and users.totp_match(key, "abcdef") is None
   and users.totp_match(key, "12345") is None and users.totp_match(key, "1234567") is None)
ok("a wrong code says the one sentence", str(raises(lambda: main.auth_code(main.CodeIn(ticket=t2["ticket"], code="000000"), REQ))) == "401"
   and users.CODE_REFUSED == "That code didn't work. Codes change every 30 seconds.")
ok("...and the ticket stays live after a wrong code", users.peek_token(t2["ticket"], ("mfa",))[0] is not None)
rc = main.auth_code(main.CodeIn(ticket=t2["ticket"], code=codes[0].lower().replace("-", "")), REQ)
ok("⭐ a recovery code works instead (case and dash do not matter)", cookie_of(rc) and rc.body["recovery_left"] == 9)
t3 = users.start_two_step(users.get_user(bob["id"]))
ok("🔴 ...once only", raises(lambda: main.auth_code(main.CodeIn(ticket=t3["ticket"], code=codes[0]), REQ)) == 401)
ok("the audit row says which second step was used",
   any(r["kind"] == "signin" and "recovery code" in (r["detail"] or "") for r in users.audit_rows()))
for _ in range(4):
    raises(lambda: main.auth_code(main.CodeIn(ticket=t3["ticket"], code="111111"), REQ))
ok("🔴 five wrong codes (with the one before) lock the address for 15 minutes, as passwords do",
   raises(lambda: main.auth_code(main.CodeIn(ticket=t3["ticket"], code=code_for(key)), REQ)) == 429)
at(minutes=30)
ok("🔴 a ticket lasts 10 minutes", raises(lambda: main.auth_code(main.CodeIn(ticket=t3["ticket"], code=code_for(key)), REQ)) == 410)
t4 = main.auth_signin(main.SignInIn(email="bob@example.org", password=GOOD_PW), REQ)
ok("🔴 a ticket opens nothing by itself: it is not a session",
   access.resolve_request(None, t4["ticket"]) is None and users.resolve_session(t4["ticket"]) == (None, None))
ok("🔴 the code step on a key not yet set up is refused", raises(lambda: main.auth_code(
    main.CodeIn(ticket=main.auth_signin(main.SignInIn(email="ada@example.org", password=GOOD_PW), REQ)["ticket"],
                code="123456"), REQ)) == 409)
# new recovery codes, signed in
s_b = cookie_of(step2(t4))["value"]
tok = as_(access.resolve_request(None, s_b))
ok("describe() carries two-step and the codes left (the account menu)",
   main.auth_me()["access"]["two_step"] is True and main.auth_me()["access"]["recovery_left"] == 9)
at(minutes=31)
ok("new recovery codes need a code from the app", raises(lambda: main.auth_recovery_codes(main.OwnCodeIn(code="000000"), REQ)) == 400)
new = main.auth_recovery_codes(main.OwnCodeIn(code=code_for(key)), REQ)["recovery_codes"]
ok("⭐ ...then ten new ones, and the old ones stop working",
   len(new) == 10 and not set(new) & set(codes) and users.recovery_left(users.get_user(bob["id"])) == 10
   and not users.use_recovery_code(users.get_user(bob["id"]), codes[1]))
access._ACCESS.reset(tok)
# an admin resets a lost phone
on2(ada["id"])
s_a, _ = users.create_session(ada["id"])
tok = as_(access.resolve_request(None, s_a))
ok("🔴 an admin cannot reset their own two-step (a recovery code, or the recovery command)",
   raises(lambda: main.admin_user_two_step_reset(ada["id"], None)) == 400)
rr = main.admin_user_two_step_reset(bob["id"], None)
ok("⭐ Reset two-step: key and codes gone, every session of the login ended, in the activity log",
   rr["user"]["two_step"] is False and users.resolve_session(s_b) == (None, None)
   and users.recovery_left(users.get_user(bob["id"])) == 0
   and any(r["kind"] == "two-step-reset" and "Ada Lovelace" in r["actor_label"] for r in users.audit_rows()))
ok("...a second reset is refused (nothing to reset)", raises(lambda: main.admin_user_two_step_reset(bob["id"], None)) == 400)
ok("...and the next sign-in is the set-up step again",
   main.auth_signin(main.SignInIn(email="bob@example.org", password=GOOD_PW), REQ)["step"] == "setup")
access._ACCESS.reset(tok)
tok = as_(users.access_for(users.get_user(bob["id"])))
ok("🔴 a non-admin cannot reset anyone's two-step", raises(lambda: main.admin_user_two_step_reset(ada["id"], None)) == 403)
access._ACCESS.reset(tok)
ok("🔴 a demo link signs a lead in with no second step",
   cookie_of(main.auth_link(main.TokenIn(token=users.demo_login("lead@example.org", "Lea Lead")["link"].split("#demo=")[1]), REQ)))

# the first admin on a new deployment (FIRST_ADMIN_EMAIL) and the recovery command
reset_db()
os.environ.pop("FIRST_ADMIN_EMAIL", None)
ok("FIRST_ADMIN_EMAIL unset: nothing happens", users.ensure_first_admin() == "off" and not users.list_users())
os.environ["FIRST_ADMIN_EMAIL"] = "not an address"
ok("...a bad address: nothing made", users.ensure_first_admin() == "bad-email" and not users.list_users())
os.environ["FIRST_ADMIN_EMAIL"] = " Boss@Example.org "
fa = users.ensure_first_admin()
boss = users.find_by_email("boss@example.org")
ok("⭐ F3 c: with no admin yet, an admin login is made and its invite issued (no sender: the link goes to the log)",
   fa == "logged" and boss and boss["role"] == "admin" and boss["name"] == "boss"
   and db.query("SELECT COUNT(*) AS n FROM auth_tokens WHERE purpose = 'invite'")[0]["n"] == 1)
ok("...once an admin exists, a restart does nothing (no second invite)", users.ensure_first_admin() == "exists"
   and db.query("SELECT COUNT(*) AS n FROM auth_tokens WHERE purpose = 'invite'")[0]["n"] == 1)
ok("...the activity log names FIRST_ADMIN_EMAIL", any(r["kind"] == "first-admin" for r in users.audit_rows()))
os.environ.pop("FIRST_ADMIN_EMAIL")
ok("the lifespan calls ensure_first_admin after the tables exist",
   MAIN.find("db.init_users_db()") < MAIN.find("users.ensure_first_admin()"))
users.set_password(boss["id"], GOOD_PW); on2(boss["id"])
s_boss, _ = users.create_session(boss["id"])
url, err = users.recover_admin("boss@example.org")
ok("⭐ the recovery command: a reset link, two-step cleared, every session ended",
   err is None and "#reset=" in url and not users.two_step_on(users.get_user(boss["id"]))
   and users.resolve_session(s_boss) == (None, None))
url2, err2 = users.recover_admin("new@example.org")
ok("...an unknown address becomes an admin with an invite link", err2 is None and "#invite=" in url2
   and users.find_by_email("new@example.org")["role"] == "admin")
ok("...a team login named in it becomes an enabled admin",
   users.recover_admin(users.create_user("t@example.org", "T", "team", "IPT1")[0]["email"])[1] is None
   and users.find_by_email("t@example.org")["role"] == "admin" and users.find_by_email("t@example.org")["team"] is None)
ok("...a bad address is refused", users.recover_admin("nope")[1] is not None)
ok("...and each run is in the activity log", sum(r["kind"] == "recovery-command" for r in users.audit_rows()) == 3)
REC = open(os.path.join(BACKEND, "recover_admin.py"), encoding="utf-8").read()
ok("recover_admin.py prints the link and sends nothing",
   "users.recover_admin(argv[1])" in REC and "print(url)" in REC and "send" not in REC.replace("sent", ""))
ok("render.yaml and env.example document FIRST_ADMIN_EMAIL and DEMO_LEADS",
   all("FIRST_ADMIN_EMAIL" in open(os.path.join(ROOT, f), encoding="utf-8").read()
       and "DEMO_LEADS" in open(os.path.join(ROOT, f), encoding="utf-8").read() for f in ("render.yaml", "env.example")))
ok("segno is pinned in requirements.txt (the QR code)",
   "segno==1.6.6" in open(os.path.join(BACKEND, "requirements.txt"), encoding="utf-8").read())

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
