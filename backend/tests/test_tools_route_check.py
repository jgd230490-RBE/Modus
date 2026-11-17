"""
test_tools_route_check.py — the route check request form, the store the tools share and the email to John
(claude/tools-route-check-request, 16 Nov 2026). No FastAPI needed; the real app's side is smoke_tools_route_check.py.

    python backend/tests/test_tools_route_check.py

Proves: the page's words against card 4 of notes/tools-first-opening-mockup-1116 (John's yes, 20:07 UTC), line by line;
the lorry picker is the planning lorries' labels from factors.json, never a key; every refusal sentence; the hidden trap;
the limit (five an hour); the row kept with the address as a hash and nothing else of the visitor; no BOOLEAN compared
with 1; the email built for John only, with no secret, and never sent in a test; the CSV; the table's place (in
NO_DATA_TABLES, untenanted, in no package list); main.py's wiring.
NOT proved: a real SMTP session, Postgres, a browser (the UI audit and the smoke harness cover the page and the app).
"""
import json
import os
import re
import sys
import tempfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

for v in ("DATABASE_URL", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL", "DEMO_REPLY_TO"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-route-check", "GATE_SECRET": "gate-secret-route-check",
                   "PLANNER_CODE": "planner-secret-rc", "MAP_PASSWORD": "map-pass-rc"})
TMP = tempfile.mkdtemp(prefix="wayscope_route_check_")
from portable import remove_scratch_db  # noqa: E402
import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import demo_request  # noqa: E402
import tools_leads  # noqa: E402
import tools_public  # noqa: E402
import tools_route_check as rc  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label}  {extra}"[:600])


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def reset_db():
    remove_scratch_db(db, TMP)
    db.init_tool_leads_db()


reset_db()

# =========================================================================== #
#  1. the page, against card 4                                                 #
# =========================================================================== #
PAGE = read("frontend/tools/route-check.html")
JS = read("frontend/tools/route-check.js")
FACTORS = json.loads(read("backend/factors.json"))


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.out.append(" ".join(data.split()))


_t = Text()
_t.feed(PAGE)
TEXT = _t.out
joined = "\n".join(TEXT)

for line in ("Route check",
             "Which road should the lorries take?",
             "Tell us where the load starts and ends and the lorry. We compare the roads a lorry of that size can take and send you the report.",
             "Collisions recorded on each road, 2021 to 2025",
             "Left turns, cycle routes, schools and hospitals passed",
             "Lorry limits",
             "Time, busy hours and carbon for a round trip",
             "A summary page for your route risk assessment",
             "By request",
             "England only for now. A planning estimate. The planner decides.",
             "Ask for a route check",
             "From", "To", "Lorry", "Loads, if you know them", "Your name", "Email", "Company, if you have one",
             "Anything we should know",
             "Nothing is charged now. We reply by email.",
             "Thanks. We have your request.",
             "We will write to you at the email you gave."):
    ok(f"card 4 line is on the page: {line[:50]}", line in TEXT or line in joined, line)
ok("card 4 line: the privacy sentence and its link",
   "We use your details to answer this request. Read the" in " ".join(TEXT)
   and '<a href="https://wayscope.co.uk/privacy.html">privacy notice</a>.' in PAGE)
ok("🔴 the page's order is the card's: pitch, then From, To, Lorry, Loads, name, email, company, note, button, thanks",
   [PAGE.find(x) for x in ('name="from"', 'name="to"', 'name="lorry"', 'name="loads"', 'name="name"', 'name="email"',
                           'name="company"', 'name="note"', 'class="btn btn-orange">Ask for a route check', 'id="rc-thanks"')]
   == sorted(PAGE.find(x) for x in ('name="from"', 'name="to"', 'name="lorry"', 'name="loads"', 'name="name"', 'name="email"',
                                    'name="company"', 'name="note"', 'class="btn btn-orange">Ask for a route check', 'id="rc-thanks"'))
   and PAGE.find("Which road should") < PAGE.find('name="from"'))
ok("🔴 exactly the eight boxes the card draws (plus the hidden trap), no more",
   sorted(re.findall(r'<(?:input|select|textarea)[^>]*name="([a-z]+)"', PAGE)) == sorted(
       ["from", "to", "lorry", "loads", "name", "email", "company", "note", "website"]))
ok("required: From, To, Lorry, name, email only", sorted(re.findall(r'name="([a-z]+)"[^>]*\brequired\b', PAGE)) == sorted(
    ["from", "to", "lorry", "name", "email"]))
ok("one h1, the heading; the list has five lines", PAGE.count("<h1") == 1 and PAGE.count("<li>") == 5)
ok("the thanks block starts hidden and the failure line is a status paragraph",
   'id="rc-thanks" hidden' in PAGE and '<p class="say" role="status"></p>' in PAGE)
ok("🔴 no price, no credit, no account, no sign-in word, no company asked for as required",
   not re.search(r"(?i)\b(price|credit|account|sign in|log in|vat|£)\b", joined) and 'name="company" ' in PAGE
   and not re.search(r'name="company"[^>]*required', PAGE))
ok("no picture of a map, no Street View, no outside script", "<img" in PAGE and PAGE.count("<img") == 1
   and not re.search(r"(?i)street ?view|mapbox|here\.com", PAGE) and "http" not in re.sub(r'(href|src)="https://(wayscope\.co\.uk|fonts\.g)[^"]*"', "", PAGE).replace("https://www.w3", ""))
ok("the script is its own file, no inline script, and posts to the one open call",
   re.search(r"<script>", PAGE) is None and '<script src="/tools/route-check.js"></script>' in PAGE
   and "/api/tools/route-check/request" in JS and "credentials" not in JS)
ok("the page script sends the trap box along", 'form.elements.website.value' in JS)

# the lorry picker: the planning lorries' labels, in the shipped order, never a key
opts = [re.sub(r"<[^>]+>", "", o).strip() for o in re.findall(r"<option[^>]*>([^<]*)</option>", PAGE)]
opts = [o.replace("&sup3;", "³") for o in opts if o]
labels = rc.lorry_labels()
ok("⭐ the Lorry picker is the planning lorries by their labels, in the shipped order", opts == labels, f"{opts} vs {labels}")
ok("...six of them, and none is a key (no 'Truck mixer')", len(labels) == 6 and not any("Truck mixer" in o for o in opts)
   and "Concrete mixer 8 m³ (32t)" in opts)
ok("...and the first option is empty (nothing is chosen for the person)", re.search(r'<select name="lorry" required>\s*<option value=""></option>', PAGE))

# =========================================================================== #
#  2. validation: every refusal is one plain sentence                          #
# =========================================================================== #
GOOD = {"from": "Harborough Rail Freight Terminal", "to": "Harborough Compound", "lorry": "Artic Flatbed (44t)", "loads": "90",
        "name": "Ada Example", "email": "Ada@Example.org", "company": "", "note": "", "website": ""}
clean, say = rc.validate(GOOD)
ok("a good request validates; the email is lower-cased; loads is a whole number",
   say is None and clean["email"] == "ada@example.org" and clean["loads"] == 90 and clean["company"] == "")
ok("loads is optional, and '1,200' reads as 1200", rc.validate(dict(GOOD, loads=""))[0]["loads"] is None
   and rc.validate(dict(GOOD, loads="1,200"))[0]["loads"] == 1200 and rc.validate(dict(GOOD, loads=12))[0]["loads"] == 12)
REFUSALS = [
    (dict(GOOD, **{"from": "  "}), "Type where the load starts."),
    (dict(GOOD, to=""), "Type where the load ends."),
    (dict(GOOD, lorry=""), "Pick the lorry."),
    (dict(GOOD, lorry="Artic Tipper"), "Pick the lorry."),
    (dict(GOOD, lorry="Truck mixer 8 m³ (32t)"), "Pick the lorry."),
    (dict(GOOD, loads="many"), "Type the loads as a whole number, or leave it empty."),
    (dict(GOOD, loads="0"), "Type the loads as a whole number, or leave it empty."),
    (dict(GOOD, loads="-4"), "Type the loads as a whole number, or leave it empty."),
    (dict(GOOD, loads="1000000"), "Type the loads as a whole number, or leave it empty."),
    (dict(GOOD, loads=2.5), "Type the loads as a whole number, or leave it empty."),
    (dict(GOOD, name=""), "Type your name."),
    (dict(GOOD, email=""), "Type an email address we can write to."),
    (dict(GOOD, email="not-an-email"), "Type an email address we can write to."),
    (dict(GOOD, email="a@b"), "Type an email address we can write to."),
    (dict(GOOD, email="a b@example.org"), "Type an email address we can write to."),
    (dict(GOOD, email="a" * 195 + "@b.org"), "Type an email address we can write to."),
    (dict(GOOD, **{"from": "x" * 201}), "The start is too long."),
    (dict(GOOD, to="x" * 201), "The end is too long."),
    (dict(GOOD, name="x" * 121), "The name is too long."),
    (dict(GOOD, company="x" * 161), "The company is too long."),
    (dict(GOOD, note="x" * 301), "The note is too long."),
    ([1, 2], "That did not work. Please try again in a minute."),
]
for body, sentence in REFUSALS:
    c, s = rc.validate(body)
    ok(f"refused in one sentence: {sentence}", c is None and s == sentence, str(s))
ok("every sentence is plain: one sentence, no number of calls, no status, no word a person must not read",
   all(len(s.split(". ")) <= 2 and not re.search(r"\d{3}|json|server|endpoint|api|token", s, re.I) for _, s in REFUSALS))
ok("the caps are the landing form's: name 120, email 200, company 160; the note 300 as its 'wants'",
   rc.MAX_LEN["name"] == demo_request.MAX_LEN["name"] and rc.MAX_LEN["email"] == demo_request.MAX_LEN["email"]
   and rc.MAX_LEN["company"] == demo_request.MAX_LEN["organisation"] and rc.MAX_LEN["note"] == demo_request.MAX_LEN["wants"])
ok("...and the page's maxlength boxes equal the caps",
   all(f'name="{n}" maxlength="{c}"' in PAGE or f'name="{n}" maxlength="{c}"' in PAGE.replace('type="text" ', "").replace('type="email" ', "")
       for n, c in (("from", 200), ("to", 200), ("name", 120), ("email", 200), ("company", 160), ("note", 300))), "")

# refuse() raises the open-call refusal with {"detail": {"say": ...}}
try:
    rc.handle(dict(GOOD, to=""), "203.0.113.9")
    raised = None
except Exception as e:  # noqa: BLE001
    raised = e
ok("a bad box raises the open-call refusal: status 400 and the sentence as detail.say",
   raised is not None and getattr(raised, "status_code", None) == 400
   and getattr(raised, "detail", None) == {"say": "Type where the load ends."})
ok("...and keeps nothing", db.query("SELECT COUNT(*) AS n FROM tool_leads")[0]["n"] == 0)

# =========================================================================== #
#  3. the trap and the row                                                     #
# =========================================================================== #
r = rc.handle(dict(GOOD, website="http://spam"), "203.0.113.9")
ok("🔴 the filled trap box is told it worked and keeps nothing", r == {"ok": True, "request_id": None}
   and db.query("SELECT COUNT(*) AS n FROM tool_leads")[0]["n"] == 0)
ok("🔴 ...even when the other boxes are bad (the machine learns nothing)",
   rc.handle({"website": "x"}, "203.0.113.9")["request_id"] is None)

IP = "203.0.113.77"
r = rc.handle(dict(GOOD, company="Example Civils", note="Access from the north only"), IP)
rid = r["request_id"]
row = db.query("SELECT * FROM tool_leads")[0]
det = json.loads(row["details"])
ok("⭐ one row is kept for a good request", r["ok"] is True and rid and row["id"] == rid and row["kind"] == "route-check")
ok("...with the person's boxes: email lower-cased, name, company, news 0",
   row["email"] == "ada@example.org" and row["name"] == "Ada Example" and row["company"] == "Example Civils"
   and row["news"] == 0)
ok("...and From, To, the lorry's label, the loads and the note in details",
   det == {"from": GOOD["from"], "to": GOOD["to"], "lorry": "Artic Flatbed (44t)", "loads": 90,
           "note": "Access from the north only"}, str(det))
ok("🔴 the address is kept only as a hash: no raw address anywhere in the row, 32 hex characters",
   IP not in json.dumps(row, default=str) and re.fullmatch(r"[0-9a-f]{32}", row["ip_hash"] or "")
   and row["ip_hash"] == tools_public.address_hash(IP))
ok("...and nothing else of the visitor is a column", sorted(row.keys()) == sorted(
    ["id", "kind", "created_at", "email", "name", "company", "news", "details", "ip_hash", "status"]), str(sorted(row)))
ok("the status starts 'queued' and the time is ISO UTC", row["status"] == "queued"
   and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", row["created_at"]))
for args in (("nope", "a@b.org"), ("route-check", "bad")):
    try:
        tools_leads.keep(*args)
        _bad = True
    except ValueError:
        _bad = False
    ok(f"keep{args} raises ValueError", not _bad)
k2 = tools_leads.keep("calculator-pdf", "Sam@Example.org", news=True, details={"calculator": "carbon"})
r2 = tools_leads.get(k2)
ok("the calculators' use of the same store: kind 'calculator-pdf', news kept as 1, no address kept when none is given",
   r2["kind"] == "calculator-pdf" and r2["news"] == 1 and r2["ip_hash"] == "" and r2["email"] == "sam@example.org")
ok("email_ok", tools_leads.email_ok("a@b.org") and not tools_leads.email_ok("a@b") and not tools_leads.email_ok(None)
   and not tools_leads.email_ok("x" * 201 + "@b.org"))

# =========================================================================== #
#  4. the limit                                                                #
# =========================================================================== #
L = rc.LIMIT
L.reset()
ok("the limit is five an hour for one address, as the landing form's",
   (L.most, L.window_s) == (5, 3600) and L.most == demo_request.PER_IP_PER_HOUR)
allowed = [L.hit("198.51.100.1") for _ in range(7)]
ok("🔴 the sixth call from one address is refused, others are not", allowed == [True] * 5 + [False] * 2
   and L.hit("198.51.100.2"))
ok("...with a sentence that names no count", "Too many" in L.say and not re.search(r"\d", L.say.replace("an hour", "")))
L.reset()

# =========================================================================== #
#  5. the email to John                                                        #
# =========================================================================== #
SETTINGS = {"SMTP_USER": "sender@example.org", "SMTP_PASSWORD": "app-pass-SECRET-123", "DEMO_FROM": "Wayscope <hello@example.org>",
            "DEMO_NOTIFY": "john@example.org", "host": "smtp.example.org", "port": 587, "reply_to": "john@example.org"}
msg = rc.notify_message(tools_leads.get(rid), SETTINGS)
body = msg.get_content()
ok("⭐ the email: subject 'Route check request', to John only, from the sender", msg["Subject"] == "Route check request"
   and msg["To"] == "john@example.org" and msg["From"] == SETTINGS["DEMO_FROM"] and msg["Cc"] is None and msg["Bcc"] is None)
ok("...it lists what was typed", all(x in body for x in (
    "From: Harborough Rail Freight Terminal", "To: Harborough Compound", "Lorry: Artic Flatbed (44t)", "Loads: 90",
    "Name: Ada Example", "Email: ada@example.org", "Company: Example Civils", "Note: Access from the north only")))
ok("🔴 ...and carries no secret and no address hash: no password, no token, no hash",
   not any(s in msg.as_string() for s in ("app-pass-SECRET-123", os.environ["ADMIN_TOKEN"], os.environ["GATE_SECRET"],
                                          os.environ["PLANNER_CODE"], os.environ["MAP_PASSWORD"], row["ip_hash"], IP)))
ok("...the person's address is the Reply-To, so John can answer; nothing goes TO the person", msg["Reply-To"] == "ada@example.org"
   and "ada@example.org" not in msg["To"])

SENT = []
_real_send = demo_request.send
demo_request.send = lambda m, s: SENT.append(m)          # never a real session
try:
    ok("deliver() with no sender configured marks the row 'unsent' and sends nothing",
       rc.deliver(rid) == "unsent" and tools_leads.get(rid)["status"] == "unsent: SMTP not configured" and not SENT)
    for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
        os.environ[k] = SETTINGS[k]
    ok("⭐ deliver() with a sender sends ONE email, to John, and marks the row 'sent'",
       rc.deliver(rid) == "sent" and len(SENT) == 1 and SENT[0]["To"] == "john@example.org"
       and tools_leads.get(rid)["status"] == "sent")

    def _boom(m, s):
        raise OSError("smtp down: app-pass-SECRET-123")
    demo_request.send = _boom
    ok("🔴 a send that fails never raises: the request is kept and marked 'failed: OSError' (no message text kept)",
       rc.deliver(rid) == "failed" and tools_leads.get(rid)["status"] == "failed: OSError"
       and "SECRET" not in json.dumps(tools_leads.get(rid), default=str)
       and tools_leads.get(rid)["email"] == "ada@example.org")
    ok("a missing row is 'missing', not an error", rc.deliver("0" * 32) == "missing")
finally:
    demo_request.send = _real_send
    for k in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY"):
        os.environ.pop(k, None)

# =========================================================================== #
#  6. the admin CSV                                                            #
# =========================================================================== #
text = tools_leads.csv_export()
lines = text.strip().split("\n")
ok("the CSV: a header and one line a row, newest first; no address hash column",
   lines[0] == "created_at,kind,name,email,company,news,details,status,id" and len(lines) == 3 and "ip_hash" not in lines[0]
   and row["ip_hash"] not in text and IP not in text)
ok("...the news column reads yes / no", ",no," in text and ",yes," in text)

# =========================================================================== #
#  7. the table's place and main.py's wiring                                   #
# =========================================================================== #
MAIN = read("backend/main.py")
DBSRC = read("backend/db.py")
MK = read("backend/tools/make_demo_tenant.py")
ok("⭐ tool_leads is in db.NO_DATA_TABLES (a public send must not empty the kept reads)", "tool_leads" in db.NO_DATA_TABLES
   and db.written_table("INSERT INTO tool_leads (a) VALUES (?)") == "tool_leads")
ok("🔴 ...is not tenanted, is in no package list and is not in make_demo_tenant's LIVE_TABLES",
   "tool_leads" not in getattr(db, "TENANTED_TABLES", ()) and not re.search(r"LIVE_TABLES = \([^)]*tool_leads", MK)
   and not re.search(r"tool_leads", MK))
ok("🔴 ...and no BOOLEAN compared with 1 in its SQL", not re.search(r"news\s*=\s*1|news\s*=\s*true", read("backend/tools_leads.py") + read("backend/tools_route_check.py"), re.I))
ok("the table is made at start-up, after demo_requests and before the users", 0 < MAIN.find("db.init_demo_requests_db()")
   < MAIN.find("db.init_tool_leads_db()") < MAIN.find("db.init_users_db()"))
ok("the open call: guarded first, listed in OPEN_ROUTES, the email as a background task, no audit",
   '@app.post("/api/tools/route-check/request")' in MAIN
   and "tools_public.guard(request, tools_route_check.LIMIT)" in MAIN
   and MAIN.index("tools_public.guard(request, tools_route_check.LIMIT)") < MAIN.index("await request.json()", MAIN.index('"/api/tools/route-check/request"'))
   and "background=_TRCTask(tools_route_check.deliver, rid)" in MAIN
   and "/api/tools/route-check/request" in tools_public.OPEN_ROUTES)
ok("...and it never reads the visitor's session or a cookie", "access.current()" not in
   MAIN[MAIN.index('"/api/tools/route-check/request"'):MAIN.index('"/api/admin/tool-leads.csv"')])
_csv = MAIN[MAIN.index('"/api/admin/tool-leads.csv"'):]
ok("the CSV read is admin only (_check_admin first) and not stored by a browser", "_check_admin(token)" in _csv[:400]
   and "no-store" in _csv[:900])
ok("/api/tools/ writes no audit row (tools_public rule 6)", '"/api/tools/"' in MAIN[MAIN.index("AUDIT_SKIP_PREFIXES"):MAIN.index("AUDIT_SKIP_PREFIXES") + 600])
ok("the page is in the UI audit's list", re.search(r'const TOOL_PAGES = \[[^\]]*"route-check"', read("backend/tests/ui_audit.js")))

# a page's own script is served beside its page, and only there
_pf = tools_public.page_file("route-check.js")
ok("⭐ page_file serves /tools/route-check.js as javascript beside its page; no page, no script; no path tricks",
   _pf is not None and _pf[1].startswith("text/javascript") and tools_public.page_file("no-such-page.js") is None
   and tools_public.page_file("index.js") is None and tools_public.page_file("..%2fmain.js") is None
   and tools_public.page_file("a/b.js") is None and tools_public.page_file(".js") is None)

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\ntest_tools_route_check.py: {PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
