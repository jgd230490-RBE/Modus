"""
H9 (8 Oct 2026) — demo requests from the landing page: backend/demo_request.py, the
demo_requests table, the gate exemption, the env-var documentation.

Run from the repo root:  python backend/tests/test_demo_request.py

What this proves, on a scratch SQLite database with SMTP stubbed: validation (required
fields, length caps, email shape, the role list, the honeypot); the salted IP hash; the
per-IP and per-email limits read from the table; the three outcomes of handle() — queued
(email mode), screen (no sender), thanks/error; the email carries the demo link, BOTH codes
and the fictional sentence and NEVER the planner or admin code or the admin token; the
notification copy; deliver() records sent / failed on the row and never raises; the
on-screen page carries the same; the CSV; main.py wires the endpoint, the 303s, the
background task and the admin CSV behind _check_admin; render.yaml and env.example list
the six variables; the gate opens exactly one path.

What it does not prove: a real SMTP session with Google (the user's live send), inbox
placement, or the HTTP layer (http_smoke.py drives the real app).

14 Oct 2026 (G3 / HU14): the email and the on-screen page carry the lead's OWN link and its
expiry, and NO shared code and NO map password. The assertions that pinned both codes in them
are REVERSED below (each says so), not deleted. New: the personal login (made, renewed, refused
for a staff or a disabled address), the notification's login line, the CSV's login columns.
"""
import datetime
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

TMP = tempfile.mkdtemp(prefix="wayscope_demo_req_")
from portable import remove_scratch_db   # tests/portable.py: Windows cannot unlink an open SQLite file
for v in ("DATABASE_URL", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL",
          "DEMO_TEAM_CODE_VAR", "DEMO_REPLY_TO"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-for-tests", "PLANNER_CODE": "planner-secret-xyz",
                   "ADMIN_CODE": "admin-secret-xyz", "IPT1_CODE": "north-team-code",
                   "IPT2_CODE": "central-team-code", "MAP_PASSWORD": "map-pass-abc",
                   "GATE_SECRET": "gate-secret-for-tests"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import demo_request as dr  # noqa: E402
import gate  # noqa: E402
import users  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_demo_requests_db()
    db.init_users_db()          # G3: a lead's own login lives in users / auth_tokens


T0 = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.timezone.utc)
users.NOW = T0                  # G3: deliver() makes the login on its own clock; pin it
T0_EXPIRES = "Thu 22 Oct 2026"  # T0 + 14 days (D48)
GOOD = {"name": "Ada Example", "email": "Ada@Example.org", "organisation": "Example Civils",
        "role": "Principal contractor", "wants": "the look-ahead", "updates": "yes", "website": ""}

# =========================================================================== #
#  1. validation                                                               #
# =========================================================================== #
clean, err = dr.validate(GOOD)
ok("a good form validates", err is None and clean["name"] == "Ada Example")
ok("...the email is lower-cased and the opt-in is a bool", clean["email"] == "ada@example.org" and clean["updates_opt_in"] is True)
ok("the updates box unticked → opt-in False", dr.validate(dict(GOOD, updates=""))[0]["updates_opt_in"] is False)
for k in ("name", "email", "organisation", "role"):
    ok(f"missing {k} is refused", dr.validate(dict(GOOD, **{k: "  "}))[1] == f"{k} missing")
ok("'wants' is optional", dr.validate(dict(GOOD, wants=""))[1] is None)
ok("🔴 a filled honeypot is 'honeypot', not an error the bot can read",
   dr.validate(dict(GOOD, website="http://spam"))[1] == "honeypot")
ok("a malformed email is refused", dr.validate(dict(GOOD, email="not-an-email"))[1] == "email malformed"
   and dr.validate(dict(GOOD, email="a@b"))[1] == "email malformed")
ok("an unknown role is refused", dr.validate(dict(GOOD, role="Hacker"))[1] == "role unknown")
ok("every field has a cap and an over-long one is refused",
   dr.validate(dict(GOOD, wants="x" * 301))[1] == "wants too long"
   and dr.validate(dict(GOOD, name="x" * 121))[1] == "name too long")
ok("the seven roles match the landing page's select, in order",
   list(dr.ROLES) == ["Client or highway authority", "Principal contractor", "Logistics or site management",
                      "Haulier or fleet operator", "Local authority officer", "Consultant", "Other"])
_landing = open(os.path.join(ROOT, "landing", "index.html"), encoding="utf-8").read()
ok("...and the page's options ARE those roles", [o for o in re.findall(r"<option>([^<]+)</option>", _landing)] == list(dr.ROLES))
ok("...and the page's field names are the ones validate() reads",
   all(f'name="{n}"' in _landing for n in ("name", "email", "organisation", "role", "wants", "updates", dr.HONEYPOT)))
ok("...and the page's maxlength caps equal MAX_LEN",
   all(f'name="{n}" type="{t}" required maxlength="{dr.MAX_LEN[n]}"' in _landing
       for n, t in (("name", "text"), ("email", "email"), ("organisation", "text")))
   and f'name="wants" type="text" maxlength="{dr.MAX_LEN["wants"]}"' in _landing)
ok("list values (a repeated field) take the first", dr.validate(dict(GOOD, name=["Ada", "Eve"]))[0]["name"] == "Ada")

# =========================================================================== #
#  2. the IP hash and the limits                                               #
# =========================================================================== #
h1 = dr.ip_hash("203.0.113.7")
ok("the IP is hashed with the gate secret as salt, 32 hex chars", re.fullmatch(r"[0-9a-f]{32}", h1) is not None
   and h1 != dr.ip_hash("203.0.113.8") and "203.0.113.7" not in h1)
_salt = os.environ.pop("GATE_SECRET")
ok("...a different salt gives a different hash (so the hash cannot be rebuilt without the deployment's secret)",
   dr.ip_hash("203.0.113.7") != h1)
os.environ["GATE_SECRET"] = _salt
ok("client_ip takes the first X-Forwarded-For entry (Render proxies), else the peer",
   dr.client_ip("198.51.100.4, 10.0.0.1", "10.0.0.9") == "198.51.100.4" and dr.client_ip("", "10.0.0.9") == "10.0.0.9"
   and dr.client_ip(None, None) == "")

reset_db()
ok("no rows → under both limits", not dr.ip_over_limit(h1, T0) and not dr.email_recent("ada@example.org", T0))
for i in range(dr.PER_IP_PER_HOUR):
    dr.store(dict(clean, email=f"p{i}@example.org"), h1, "sent", T0 - datetime.timedelta(minutes=5 * i))
ok(f"{dr.PER_IP_PER_HOUR} requests from one IP inside the hour → over the limit", dr.ip_over_limit(h1, T0))
ok("...but an hour later they no longer count", not dr.ip_over_limit(h1, T0 + datetime.timedelta(minutes=61)))
ok("...and another IP is unaffected", not dr.ip_over_limit(dr.ip_hash("203.0.113.8"), T0))
ok("an email seen 5 minutes ago is 'recent'; one seen 11 minutes ago is not",
   dr.email_recent("p1@example.org", T0) and not dr.email_recent("p1@example.org", T0 + datetime.timedelta(minutes=11)))

# =========================================================================== #
#  3. handle(): the outcomes                                                   #
# =========================================================================== #
reset_db()
r = dr.handle(dict(GOOD, website="bot"), "203.0.113.7", T0)
ok("🔴 honeypot → 'thanks' and NOTHING stored", r["outcome"] == "thanks" and r["reason"] == "honeypot"
   and db.query("SELECT COUNT(*) AS n FROM demo_requests")[0]["n"] == 0)
r = dr.handle(dict(GOOD, email="nope"), "203.0.113.7", T0)
ok("invalid form → 'error', nothing stored", r["outcome"] == "error" and db.query("SELECT COUNT(*) AS n FROM demo_requests")[0]["n"] == 0)

# --- no sender configured: the on-screen mode
ok("with no SMTP variables smtp_settings() is None", dr.smtp_settings() is None)
r = dr.handle(GOOD, "203.0.113.7", T0)
# REVERSED 14 Oct 2026 (G3 / HU14): the screen outcome used to carry BOTH shared codes; it now carries the lead's own link
ok("⭐ no sender → 'screen' with the name and the lead's OWN link and its expiry, and no codes",
   r["outcome"] == "screen" and r["name"] == "Ada Example" and "codes" not in r
   and r["access"]["status"] == "new" and r["access"]["link"].startswith("https://app.wayscope.co.uk/#demo=")
   and r["access"]["expires_on"] == T0_EXPIRES)
_lead = users.find_by_email("ada@example.org")
ok("...a demo login was made for the lead: their team slot, 14 days, linked to the request, no password",
   _lead and _lead["kind"] == "demo" and _lead["role"] == "team" and _lead["team"] == "IPT1"
   and _lead["expires_at"] == "2026-10-22T12:00:00Z" and _lead["demo_request_id"] == r["request_id"]
   and not _lead["password_hash"])
_raw = r["access"]["link"].split("#demo=", 1)[1]
ok("🔴 the raw link is in no table — only its hash",
   not any(_raw in str(db.query(f"SELECT * FROM {t}")) for t in ("demo_requests", "users", "auth_tokens")))
row = dr.get(r["request_id"])
ok("...the row is stored and marked shown on screen", row and row["email_status"] == dr.STATUS_SCREEN
   and row["email"] == "ada@example.org" and row["updates_opt_in"] in (1, True) and row["ip_hash"] == h1)
ok("...and the row holds NO code and NO raw IP",
   not any(v in str(row) for v in ("map-pass-abc", "north-team-code", "203.0.113.7")))
page = dr.access_page(r["name"], r["access"])
# REVERSED 14 Oct 2026 (G3 / HU14): the page carried both codes; it now carries the personal link and NEITHER code
ok("⭐ the on-screen page carries the personal link, its expiry, the fictional sentence and the three things to try",
   r["access"]["link"] in page and T0_EXPIRES in page and "fictional" in page
   and "Dashboard" in page and "Look-ahead" in page and "Public map" in page and "Corridor map" not in page and "Hello Ada" in page)   # 11 Oct 2026 NARROWED: renamed
ok("🔴 ...and NO shared code, NO map password and no 'shared with everyone' (HU14)",
   "map-pass-abc" not in page and "north-team-code" not in page and "Team access code" not in page
   and "Public map password" not in page and "shared with everyone" not in page)
ok("...and never the planner / admin code or the admin token",
   not any(s in page for s in ("planner-secret-xyz", "admin-secret-xyz", "adm-token-for-tests")))
ok("...it is noindex, links the privacy notice and loads no script",
   'name="robots" content="noindex"' in page and "/privacy.html" in page and "<script" not in page)
ok("...and HTML in a name is escaped", "<b>x</b>" not in dr.access_page("<b>x</b>", r["access"]) and "&lt;b&gt;x" in dr.access_page("<b>x</b>", r["access"]))
os.environ["DEMO_TEAM_CODE_VAR"] = "IPT2_CODE"
ok("DEMO_TEAM_CODE_VAR picks which team code travels", dr.codes()["team"] == "central-team-code")
os.environ.pop("DEMO_TEAM_CODE_VAR")
ok("...default IPT1_CODE", dr.codes()["team"] == "north-team-code")
# 14 Oct 2026 (G3 / HU14): the variable now names only the SLOT a lead's login belongs to; its value is never sent
os.environ["DEMO_TEAM_CODE_VAR"] = "IPT2_CODE"
ok("G3: DEMO_TEAM_CODE_VAR=IPT2_CODE → a lead's login is on the IPT2 slot", users.demo_slot() == "IPT2")
os.environ["DEMO_TEAM_CODE_VAR"] = "nonsense"
ok("...anything that is not a slot falls back to IPT1", users.demo_slot() == "IPT1")
os.environ.pop("DEMO_TEAM_CODE_VAR")
ok("...default IPT1", users.demo_slot() == "IPT1")
ok("🔴 the access page and the email no longer call codes()",
   "codes()" not in open(os.path.join(BACKEND, "demo_request.py"), encoding="utf-8").read().split("def codes():", 1)[1].split("\n\n\n", 1)[1])

# --- the per-IP limit in screen mode
reset_db()
for i in range(dr.PER_IP_PER_HOUR):
    ok(f"request {i + 1} from one IP is served", dr.handle(dict(GOOD, email=f"q{i}@example.org"), "203.0.113.7", T0)["outcome"] == "screen")
ok("🔴 the next one inside the hour is refused ('error'), and not stored",
   dr.handle(dict(GOOD, email="q9@example.org"), "203.0.113.7", T0)["outcome"] == "error"
   and db.query("SELECT COUNT(*) AS n FROM demo_requests")[0]["n"] == dr.PER_IP_PER_HOUR)

# --- sender configured: email mode
os.environ.update({"SMTP_USER": "sender@wayscope.co.uk", "SMTP_PASSWORD": "abcd efgh ijkl mnop",
                   "DEMO_FROM": "Wayscope <sender@wayscope.co.uk>", "DEMO_NOTIFY": "notify@wayscope.co.uk"})
s = dr.smtp_settings()
ok("with the four variables set, smtp_settings() is Google SMTP on 587 and Reply-To defaults to DEMO_NOTIFY",
   s and s["host"] == "smtp.gmail.com" and s["port"] == 587 and s["reply_to"] == "notify@wayscope.co.uk")
os.environ["DEMO_NOTIFY"] = ""
ok("...and any one of them blank → None again (fails to the on-screen mode, never to an error)", dr.smtp_settings() is None)
os.environ["DEMO_NOTIFY"] = "notify@wayscope.co.uk"

reset_db()
r = dr.handle(GOOD, "203.0.113.7", T0)
ok("⭐ sender configured → 'queued' with a request id", r["outcome"] == "queued" and dr.get(r["request_id"])["email_status"] == dr.STATUS_QUEUED)
rid = r["request_id"]
r2 = dr.handle(GOOD, "203.0.113.7", T0 + datetime.timedelta(minutes=3))
ok("🔴 the same email again inside 10 minutes → 'thanks', nothing new stored, NOT re-sent",
   r2["outcome"] == "thanks" and r2["reason"] == "repeat"
   and db.query("SELECT COUNT(*) AS n FROM demo_requests")[0]["n"] == 1)
r3 = dr.handle(GOOD, "203.0.113.7", T0 + datetime.timedelta(minutes=12))
ok("...and after 10 minutes it is queued again", r3["outcome"] == "queued")

# =========================================================================== #
#  4. the email and deliver(), SMTP stubbed                                    #
# =========================================================================== #
SENT = []


class _SMTP:
    """Records what smtplib would have done. One instance per session."""
    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls = []
        SENT.append(self)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def ehlo(self): self.calls.append("ehlo")
    def starttls(self): self.calls.append("starttls")
    def login(self, u, p): self.calls.append(("login", u, p))
    def send_message(self, msg): self.calls.append(("send", msg))
    ehlo_resp = b"250-smtp.gmail.com at your service\n250-AUTH LOGIN PLAIN XOAUTH2"
    def auth_plain(self, challenge=None): return ""
    def auth_login(self, challenge=None): return ""
    def auth(self, mech, authobject, initial_response_ok=True):
        self.calls.append(("auth", mech)); return (235, b"2.7.0 Accepted")


_real_smtp = dr.smtplib.SMTP
dr.smtplib.SMTP = _SMTP
try:
    res = dr.deliver(rid)
    ok("deliver() reports 'sent' and marks the row sent", res == "sent" and dr.get(rid)["email_status"] == dr.STATUS_SENT)
    ok("two SMTP sessions: the visitor's email, then the notification", len(SENT) == 2
       and all(x.host == "smtp.gmail.com" and x.port == 587 and x.timeout == 20 for x in SENT))
    first = SENT[0].calls
    ok("each session does STARTTLS before login, and logs in with SMTP_USER and the app password",
       first.index("starttls") < first.index(("login", "sender@wayscope.co.uk", "abcd efgh ijkl mnop")))
    msg = first[-1][1]
    ok("the visitor's email: subject, From = DEMO_FROM, To = the visitor, Reply-To = DEMO_NOTIFY",
       msg["Subject"] == "Your Wayscope demo access" and msg["From"] == "Wayscope <sender@wayscope.co.uk>"
       and msg["To"] == "ada@example.org" and msg["Reply-To"] == "notify@wayscope.co.uk")
    text = msg.get_body(preferencelist=("plain",)).get_content()
    htmlp = msg.get_body(preferencelist=("html",)).get_content()
    ok("...plain text AND HTML parts", bool(text) and bool(htmlp) and msg.is_multipart())
    _lead_link = None
    for part, label in ((text, "plain"), (htmlp, "HTML")):
        # REVERSED 14 Oct 2026 (G3 / HU14): the email carried BOTH shared codes and said the access was shared; it now
        # carries the lead's own link and its expiry, and neither code
        _m = re.search(r"https://app\.wayscope\.co\.uk/#demo=[A-Za-z0-9_-]+", part)
        _lead_link = _lead_link or (_m.group(0) if _m else None)
        ok(f"⭐ the {label} part carries the lead's own link, its expiry, the fictional sentence, the three things to try and the privacy link",
           _m is not None and T0_EXPIRES in part
           and "fictional highways scheme" in part
           and "Dashboard" in part and "Look-ahead" in part and "Public map" in part and "Corridor map" not in part
           and "https://wayscope.co.uk/privacy.html" in part and "Hello Ada" in part)
        ok(f"🔴 the {label} part carries NO shared code, NO map password and no 'shared with everyone' (HU14, D46)",
           "map-pass-abc" not in part and "north-team-code" not in part and "Team access code" not in part
           and "Public map password" not in part and "shared with everyone" not in part)
        ok(f"🔴 the {label} part never carries the planner code, the admin code or the admin token",
           not any(x in part for x in ("planner-secret-xyz", "admin-secret-xyz", "adm-token-for-tests", "PLANNER_CODE", "ADMIN")))
        ok(f"the {label} part is signed John Davis and says why they got it",
           "John Davis" in part and "requested a demo at wayscope.co.uk" in part)
    # NARROWED 11 Oct 2026 (guide v2.1 review): the copy's "approving a week as a planner" mixed two acts (lines are
    # approved, weeks are confirmed); the offer of a planner walkthrough stays, in the app's own words.
    ok("the words are the copy's (landing-copy-v2-1008.md §3): 'If you'd like a walkthrough of ... a planner', in the app's words",
       "If you'd like a walkthrough of the planner's side, approving forecasts and confirming the week" in text)
    note = SENT[1].calls[-1][1]
    ok("the notification: to DEMO_NOTIFY, one line with name, organisation, role, email, wants and updates",
       note["To"] == "notify@wayscope.co.uk" and note["Subject"].startswith("Demo request: Ada Example")
       and "Ada Example, Example Civils, Principal contractor, ada@example.org" in note.get_content()
       and "Wants to see: the look-ahead" in note.get_content() and "Updates: yes" in note.get_content())
    ok("🔴 the notification carries no code", "map-pass-abc" not in note.get_content() and "north-team-code" not in note.get_content())
    ok("G3: the notification says the lead got a personal login and until when, and carries no link",
       f"Personal login: new, works until {T0_EXPIRES}." in note.get_content() and "#demo=" not in note.get_content())
    _t, _u = users.peek_token(_lead_link.split("#demo=", 1)[1], ("demo",))
    ok("⭐ the emailed link is live: it belongs to the lead's demo login", _t is not None and _u["email"] == "ada@example.org")

    # HU14: a repeat request after the 10-minute window renews the same login and sends a NEW link
    SENT.clear()
    r5 = dr.handle(GOOD, "203.0.113.7", T0 + datetime.timedelta(minutes=30))
    users.NOW = T0 + datetime.timedelta(days=3)
    dr.deliver(r5["request_id"])
    _again = SENT[0].calls[-1][1].get_body(preferencelist=("plain",)).get_content()
    ok("HU14: a repeat request renews the SAME login for 14 days from now (one login per address)",
       db.query("SELECT COUNT(*) AS n FROM users WHERE email = 'ada@example.org'")[0]["n"] == 1
       and users.find_by_email("ada@example.org")["expires_at"] == "2026-10-25T12:00:00Z"
       and "Sun 25 Oct 2026" in _again)
    ok("...and the earlier link is retired (only the newest one works)", users.peek_token(_lead_link.split("#demo=", 1)[1], ("demo",))[0] is None)
    users.NOW = T0

    # HU14: an address that already has a STAFF login gets no demo link — they sign in as usual
    users.create_user("staff@example.org", "Sam Staff", "planner")
    SENT.clear()
    r6 = dr.handle(dict(GOOD, email="staff@example.org", name="Sam Staff"), "203.0.113.10", T0)
    dr.deliver(r6["request_id"])
    _st = SENT[0].calls[-1][1].get_body(preferencelist=("plain",)).get_content()
    ok("🔴 HU14: a staff address gets 'you already have a login', no link, and its login is untouched",
       "You already have a Wayscope login" in _st and "#demo=" not in _st
       and users.find_by_email("staff@example.org")["kind"] == "staff"
       and users.find_by_email("staff@example.org")["expires_at"] is None)

    # HU14: a lead an admin disabled stays disabled, and is not emailed
    users.update_user(users.find_by_email("ada@example.org")["id"], {"disabled": True})
    SENT.clear()
    r7 = dr.handle(GOOD, "203.0.113.11", T0 + datetime.timedelta(minutes=60))
    res7 = dr.deliver(r7["request_id"])
    ok("🔴 HU14: a disabled lead asking again is not re-enabled and gets no email (the team is notified)",
       res7 == "disabled" and users.find_by_email("ada@example.org")["disabled"] == 1
       and len(SENT) == 1 and SENT[0].calls[-1][1]["To"] == "notify@wayscope.co.uk"
       and dr.get(r7["request_id"])["email_status"] == "not sent: this lead's login is disabled")
    users.update_user(users.find_by_email("ada@example.org")["id"], {"disabled": False})

    # a failing send
    class _Boom(_SMTP):
        def login(self, u, p): raise dr.smtplib.SMTPAuthenticationError(535, b"bad app password")
        def auth(self, mech, authobject, initial_response_ok=True): raise dr.smtplib.SMTPAuthenticationError(535, b"bad app password")
    dr.smtplib.SMTP = _Boom
    r4 = dr.handle(dict(GOOD, email="new@example.org"), "203.0.113.9", T0)
    res = dr.deliver(r4["request_id"])
    row = dr.get(r4["request_id"])
    ok("🔴 a refused login never raises: the row says failed + the exception class, and the error text is kept for the CSV",
       res == "failed" and row["email_status"] == dr.STATUS_FAILED + "SMTPAuthenticationError" and "bad app password" in row["email_error"])
    ok("deliver() on an unknown id is 'missing'", dr.deliver("nope") == "missing")
    os.environ["SMTP_PASSWORD"] = ""
    ok("deliver() with the sender gone since the request → 'unsent', recorded", dr.deliver(rid) == "unsent"
       and dr.get(rid)["email_status"] == "unsent: SMTP not configured")
    os.environ["SMTP_PASSWORD"] = "abcd efgh ijkl mnop"
finally:
    dr.smtplib.SMTP = _real_smtp

# --- the probe (SMTP stubbed)
os.environ["SMTP_PASSWORD"] = ""
pr = dr.smtp_probe()
ok("probe with a variable missing: not configured, names the missing one, no session attempted",
   pr["configured"] is False and pr["missing"] == ["SMTP_PASSWORD"] and pr["step"] == "settings" and pr["ok"] is False)
os.environ["SMTP_PASSWORD"] = "abcd efgh ijkl mnop"
dr.smtplib.SMTP = _SMTP
try:
    SENT.clear()
    pr = dr.smtp_probe()
    ok("⭐ probe with a working server: connect → ehlo → starttls → AUTH PLAIN accepted, ok, nothing sent, one session",
       pr["ok"] is True and pr["step"] == "done" and pr["error"] is None and len(SENT) == 1
       and not any(isinstance(c, tuple) and c[0] == "send" for c in SENT[0].calls) and pr["user"] == "sender@wayscope.co.uk"
       and pr["attempts"][0]["mech"] == "PLAIN" and pr["attempts"][0]["code"] == 235 and "AUTH LOGIN PLAIN" in pr["attempts"][0]["ehlo"])
    ok("...it reports the password's length and spacing, never the password",
       pr["password_len"] == 19 and pr["password_has_spaces"] is True and "abcd" not in str(pr))
    dr.smtplib.SMTP = _Boom
    SENT.clear()
    pr = dr.smtp_probe()
    ok("🔴 probe with a refused login: both mechanisms tried, step 'auth', 535 and the server's words, never the password",
       pr["ok"] is False and pr["step"] == "auth" and pr["error_class"] == "SMTPAuthenticationError"
       and pr["error"] == "535 bad app password" and [a["mech"] for a in pr["attempts"]] == ["PLAIN", "LOGIN"]
       and "abcd efgh" not in str(pr) and isinstance(pr["elapsed_ms"], int) and len(SENT) == 2)
    class _Hangup(_SMTP):
        def auth(self, mech, authobject, initial_response_ok=True): raise dr.smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
    dr.smtplib.SMTP = _Hangup
    pr = dr.smtp_probe()
    ok("a server that hangs up at AUTH: the class and the EHLO capabilities are reported for each mechanism",
       pr["ok"] is False and pr["error_class"] == "SMTPServerDisconnected" and all(a["ehlo"] and a["step"] == "auth" for a in pr["attempts"]))
finally:
    dr.smtplib.SMTP = _real_smtp
_dr_src = open(os.path.join(BACKEND, "demo_request.py"), encoding="utf-8").read()
_main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("main.py serves the probe at /api/admin/diagnostics/smtp behind _check_admin",
   re.search(r'@app\.get\("/api/admin/diagnostics/smtp"\)\ndef demo_smtp_probe\(token: Optional\[str\] = None\):\n(?:    .*\n)*?    _check_admin\(token\)\n    return demo_request\.smtp_probe\(\)', _main_src) is not None)
ok("deliver() writes the outcome to the service log by request id, never an address or a code",
   all(('print(f"demo_request: {request_id} ' + w) in _dr_src for w in ("visitor email FAILED", "visitor email sent", "notification sent", "notification FAILED"))
   and not any(("email" in m and "row[" in m) for m in re.findall(r'print\(f"demo_request:[^\n]*', _dr_src)))

# =========================================================================== #
#  5. the CSV                                                                  #
# =========================================================================== #
csv_text = dr.csv_export()
lines = csv_text.strip().split("\n")
# NARROWED 14 Oct 2026 (G3 / HU14): the header is the ten columns it always had, then the six login columns
ok("the CSV has a header and one line per request, newest first",
   lines[0] == ",".join(dr.CSV_COLUMNS + dr.LOGIN_COLUMNS) and lines[0].startswith(",".join(dr.CSV_COLUMNS) + ",")
   and len(lines) == 1 + db.query("SELECT COUNT(*) AS n FROM demo_requests")[0]["n"])
_ada = users.find_by_email("ada@example.org")
users.audit_event("demo-link", user=_ada)
users.record_page(users.access_for(_ada), "dashboard")
users.record_page(users.access_for(_ada), "dashboard")
users.record_page(users.access_for(_ada), "map")
_csv2 = dr.csv_export()
_ada_line = [l for l in _csv2.strip().split("\n") if "ada@example.org" in l][0]
ok("HU14: each lead's line says who looked at what: login status, expiry, sign-ins, pages with counts",
   ",active,2026-10-25T12:00:00Z,1," in _ada_line and _ada_line.endswith(",dashboard 2 · map 1"))
ok("...a staff address reads 'staff login' and shows nothing of what that person did",
   [l for l in _csv2.strip().split("\n") if "staff@example.org" in l][0].endswith(",staff login,,,,,"))
ok("...the Users page's lead list carries the same summary and the login id",
   [x for x in dr.leads() if x["email"] == "ada@example.org"][0]["user_id"] == _ada["id"])
ok("...opt-in reads yes/no and the status column is there", ",yes," in csv_text and "failed: SMTPAuthenticationError" in csv_text)
ok("🔴 the CSV never carries a code or a raw IP",
   not any(x in csv_text for x in ("map-pass-abc", "north-team-code", "203.0.113", "planner-secret-xyz")))

# =========================================================================== #
#  6. wiring, by source: main.py, the gate, the docs                            #
# =========================================================================== #
main_src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
ok("main.py posts /api/public/demo-request and calls demo_request.handle()",
   '@app.post("/api/public/demo-request")' in main_src and "demo_request.handle(form, ip)" in main_src)
ok("...parses the body with urllib (no multipart dependency)", "parse_qs(raw, keep_blank_values=True)" in main_src
   and "python-multipart" not in open(os.path.join(BACKEND, "requirements.txt"), encoding="utf-8").read())
ok("...reads the visitor's IP through client_ip(X-Forwarded-For, peer)", 'demo_request.client_ip(request.headers.get("x-forwarded-for")' in main_src)
ok("...answers 303 to thanks.html / error.html on the landing site", main_src.count("status_code=303") == 3
   and '"/thanks.html"' in main_src and '"/error.html"' in main_src)
ok("...and the send is a BackgroundTask AFTER the redirect", "_DRTask(demo_request.deliver, result[\"request_id\"])" in main_src)
# NARROWED 14 Oct 2026 (G3 / HU14): the page is built from the personal access, not the codes
ok("...the screen outcome is an HTML response with no-store", "demo_request.access_page(result[\"name\"], result[\"access\"])" in main_src
   and "result[\"codes\"]" not in main_src)
ok("main.py serves /api/admin/demo-requests.csv behind _check_admin",
   '@app.get("/api/admin/demo-requests.csv")' in main_src
   and re.search(r'demo-requests\.csv"\)\ndef demo_requests_csv\(token: Optional\[str\] = None\):\n(?:    .*\n)*?    _check_admin\(token\)', main_src))
ok("the lifespan creates the table after the fuel index and before init_tenant()",
   0 < main_src.find("db.init_costing_db()") < main_src.find("db.init_demo_requests_db()") < main_src.find("db.init_tenant()"))
ok("the gate opens exactly this path", gate.scope_for("/api/public/demo-request") is None
   and gate.scope_for("/api/public/route-forecasts") == "map" and gate.OPEN_PATHS == ("/api/public/demo-request",))
for fn in ("render.yaml", "env.example"):
    txt = open(os.path.join(ROOT, fn), encoding="utf-8").read()
    ok(f"{fn} lists the six variables", all(k in txt for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL", "DEMO_TEAM_CODE_VAR")))
ok("render.yaml keeps every new variable sync: false (values typed in Render, never in the repo)",
   all(re.search(r"- key: %s\s*(#[^\n]*)?\n\s*sync: false" % k, open(os.path.join(ROOT, "render.yaml"), encoding="utf-8").read())
       for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY")))
ok("🔴 no code value, app password or token is written anywhere in the module",
   not re.search(r"(pk\.|[0-9a-f]{40,})", open(os.path.join(BACKEND, "demo_request.py"), encoding="utf-8").read()))
ok("the module reads the codes at call time (os.getenv inside codes()), never at import",
   re.search(r"def codes\(\):\n(?:.*\n){1,4}.*os\.getenv\(\"MAP_PASSWORD\"\)", open(os.path.join(BACKEND, "demo_request.py"), encoding="utf-8").read()) is not None)

# 11 Oct 2026 — the guide update: the email and the access page say how the tour works now (nothing pops up; the
# New here? box, the dots, Guide on the demo bar). Narrowed nothing.
# 14 Oct 2026 (G3): the email and the page take the personal access now, not the codes
_c = {"status": "new", "link": "https://app.wayscope.co.uk/#demo=abc", "expires_on": T0_EXPIRES,
      "sign_in": "https://app.wayscope.co.uk/"}
_new_guide = 'Each page offers a short tour in a small "New here?" box'
for _part, _label in ((dr.email_text("Ada Example", _c), "plain"), (dr.email_html("Ada Example", _c), "HTML"),
                      (dr.access_page("Ada Example", _c), "access page")):
    ok(f"guide update: the {_label} says nothing pops up and how to start the tour from the demo bar",
       _new_guide in _part and "Nothing pops up by itself." in _part and "DEMO · Fictional scheme" in _part   # NARROWED 15 Oct 2026
       and "starts the tour for the page you are on" in _part)
    ok(f"🔴 ...and the {_label} no longer says a guide opens on each page or sits in the corner",
       "opens on each page the first time" not in _part and "in the corner" not in _part)
    # 11 Oct 2026 (late, guide v2.1 review): the three things to try say what the pages show now. Today's figures
    # are in the Dashboard's folded "This week and today" section; the Look-ahead opens on this week.
    ok(f"🔴 the {_label}'s things to try: the Dashboard is the plan with today one click down; the Look-ahead is this week",
       "the plan at a glance; today's tonnes, trips and vehicles are one click down, under This week and today." in _part
       and "this week committed by route and by day, with closures and route caps flagged; switch to next week to plan ahead." in _part
       and "today's tonnes, trips and vehicles, and this week against plan" not in _part
       and "next week committed by route and by day" not in _part)
    ok(f"...the {_label} offers a walkthrough of approving forecasts and confirming the week, not 'approving a week'",
       "the planner's side, approving forecasts and confirming the week" in _part and "approving a week" not in _part)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
