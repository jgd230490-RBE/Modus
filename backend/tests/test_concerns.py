"""
Report a concern, 5 Nov 2026 (group 6, PR 1) — backend/concerns.py, the public send (/api/public/concerns), the staff
calls (/api/concerns...), the Config boxes and the clean-up. Mockup notes/report-concern-mockup-1105/ (Q1-Q14).

What is asserted: the table is per scheme, in the organisation file and writes no kept read away (NO_DATA_TABLES); the
form is off until ticked and, outside the demo, until a privacy link is typed; every check on what the public sends
(kind, words, links, < >, the date, the time, the registration, the pin's box, a reply needs a contact, contact dropped
when no reply is asked); the trap field; the header, type and size rules; the limits (an hour, a day, the scheme); the
answer carries the reference and nothing else; another scheme never sees a concern (list, one, ids, the count); staff
steps (reply, close, reopen, route, delete the personal details now) and who may take them; the KPI clock in working
days; the clean-up of card 9 to the day; the audit rows carry no words or contact; the alert email carries nothing
personal; the public map's gate covers the send and no /api/public/ read returns a concern.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed (http_smoke.py drives the real one); the form and the page are checked in Chrome.
  * SQLite only. The alert email is built, never sent.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_concerns.py
"""
import copy
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

# ---- stubs, as test_clp_notes.py --------------------------------------------------
_fp = types.ModuleType("flexpolyline")
_fp.decode = lambda s: []
_fp.encode = lambda pts: ""
sys.modules.setdefault("flexpolyline", _fp)


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


def _Query(default=None, **k):
    return default


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = _Query


class _Request:
    def __init__(self, headers=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


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
    def __init__(self, content=None, status_code=200, headers=None, media_type=None):
        self.body = content
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.media_type = media_type


_resp.Response = _Response
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass

    async def get_response(self, path, scope):
        return None


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_concerns_")
from portable import remove_scratch_db, offline   # noqa: E402,F401
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)
for _v in ("SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import gate  # noqa: E402
import network  # noqa: E402
import taxonomy  # noqa: E402
import tenant_package  # noqa: E402
import users  # noqa: E402
import concerns  # noqa: E402
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def refused(fn, status=None, words=None):
    """The Refused (or HTTPException) a call raises, checked for status and words; None when it did not raise."""
    try:
        fn()
    except concerns.Refused as e:
        if status is not None and e.status != status:
            return None
        if words is not None and words not in e.words:
            return None
        return e
    except _HTTPException as e:
        if status is not None and e.status_code != status:
            return None
        if words is not None and words not in str(e.detail):
            return None
        return e
    return None


# =========================================================================== #
#  0. A small scheme                                                           #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db(); db.init_users_db()
db.init_tenant()
taxonomy.seed_taxonomy()
config.invalidate()
config.seed_from_file(conversions)
config.invalidate()
access.set_current("planner123")

PIT = network.create_location("Pit West", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=["aggregate"], receives=["aggregate"])["id"]
YARD = network.create_location("Yard East", "destination", lat=52.65, lon=-0.85, loc_type="Compound", supplies=["aggregate"], receives=["aggregate"])["id"]
R1 = network.create_route(PIT, YARD, route_id="R001", ipt="IPT1")["id"]
R2 = network.create_route(YARD, PIT, route_id="R002", ipt="IPT1")["id"]
LINE = [[-0.95, 52.55], [-0.90, 52.60], [-0.85, 52.65]]
for _rid in (R1,):
    for _leg in ("loaded", "return"):
        db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
                   "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (db.current_tenant(), _rid, network.DEFAULT_PROFILE, _leg, 0, json.dumps(LINE), 14.0, 0.4,
                    "2026-11-01T00:00:00Z"))
db.bump_data_version()


def set_tenant(**kw):
    doc = copy.deepcopy(config.load(conversions, use_cache=False))
    t = doc.setdefault("tenant", {})
    for k, v in kw.items():
        if v is None:
            t.pop(k, None)
        else:
            t[k] = v
    probs = config.validate(doc)
    if probs:
        return probs
    config.save(doc, by="tester")
    config.invalidate()
    return []


NOW = datetime.datetime(2026, 11, 5, 10, 0, tzinfo=datetime.timezone.utc)
TODAY = NOW.date().isoformat()


def form(**kw):
    f = {"kind": "mud", "words": "Mud across both lanes after the lorries went through.", "happened_on": TODAY,
         "happened_time": "08:15", "lat": 52.60, "lon": -0.90}
    f.update(kw)
    return f


# =========================================================================== #
#  1. The table                                                                #
# =========================================================================== #
ok("🔴 concerns is a tenanted table", "concerns" in db.TENANTED_TABLES)
ok("🔴 concerns is in the organisation file, after routes and locations",
   "concerns" in tenant_package.ORDER and tenant_package.ORDER.index("concerns") > tenant_package.ORDER.index("routes"))
ok("🔴 a public send throws away no kept read (NO_DATA_TABLES)", "concerns" in db.NO_DATA_TABLES)
_DDL = db._TENANT_DDL["concerns"]
ok("the table keys on (tenant_id, id)", "PRIMARY KEY (tenant_id, id)" in _DDL)
ok("🔴 no BOOLEAN column (SQLite hides a Postgres boolean compared with 1)", "BOOLEAN" not in _DDL.upper())
ok("the pin is DOUBLE PRECISION (Postgres REAL rounds coordinates)", _DDL.count("DOUBLE PRECISION") == 2)

# =========================================================================== #
#  2. Off until ticked; the privacy link (Q12); Config's checks                #
# =========================================================================== #
st = concerns.settings()
ok("off by default", st["on"] is False and st["form"] is False, str(st))
ok("🔴 a send while off is refused (404) and stores nothing",
   refused(lambda: concerns.submit(form(), "ip-a", NOW), 404) is not None and concerns.new_count() == 0)
ok("ticking on a real scheme without a privacy link keeps the form off", set_tenant(concerns_on=True) == []
   and concerns.settings()["form"] is False)
ok("a privacy link turns the form on",
   set_tenant(concern_privacy_url="https://example.org/privacy") == [] and concerns.settings()["form"] is True)
ok("🔴 outside the demo a send without the privacy tick is refused (Q12)",
   refused(lambda: concerns.submit(form(), "ip-a", NOW), 422, "privacy notice") is not None and concerns.new_count() == 0)
ok("... and with it, it is taken", concerns.submit(form(privacy_ok=True), "ip-a", NOW)["ref"] == "C-0001")
db.execute("DELETE FROM concerns WHERE tenant_id = ?", (db.current_tenant(),))
ok("the demo uses Wayscope's notice when none is typed",
   set_tenant(concern_privacy_url=None, demo_notice="Fictional scheme") == []
   and concerns.settings()["privacy_url"] == concerns.DEMO_PRIVACY_URL and concerns.settings()["form"] is True)
ok("Config refuses 0 months, 73 months and a part month",
   all(set_tenant(concern_keep_months=v) for v in (0, 73, 1.5)))
ok("Config refuses a reply target of 0 or 31 days", all(set_tenant(concern_reply_days=v) for v in (0, 31)))
ok("Config refuses an http:// privacy link", bool(set_tenant(concern_privacy_url="http://example.org/p")))
ok("Config refuses concerns_on as text", bool(set_tenant(concerns_on="yes")))
ok("Config takes 6 months and 5 working days", set_tenant(concern_keep_months=6, concern_reply_days=5) == []
   and concerns.settings()["keep_months"] == 6 and concerns.settings()["reply_days"] == 5)
ok("the settings reach the map's tenant words (and /api/meta's)", (lambda t: t["concerns_on"] is True and
   t["concern_keep_months"] == 6 and t["concern_reply_days"] == 5)(config.tenant_settings(conversions)))
set_tenant(concern_keep_months=12)

# =========================================================================== #
#  3. What the public sends                                                    #
# =========================================================================== #
ok("an unknown kind is refused", refused(lambda: concerns.submit(form(kind="riot"), "ip-b", NOW), 422, "kind"))
ok("no words is refused", refused(lambda: concerns.submit(form(words="   "), "ip-b", NOW), 422, "what happened"))
ok("1,001 characters is refused", refused(lambda: concerns.submit(form(words="x" * 1001), "ip-b", NOW), 422, "1,000"))
ok("🔴 a < or > is refused", refused(lambda: concerns.submit(form(words="a <script> b"), "ip-b", NOW), 422, "< and >"))
for link in ("see https://spam.example now", "go to www.cheap.biz", "visit cheap-pills.com today"):
    ok(f"🔴 a web link is refused ({link})", refused(lambda: concerns.submit(form(words=link), "ip-b", NOW), 422, "web links"))
ok("a date in the future is refused",
   refused(lambda: concerns.submit(form(happened_on="2026-11-09"), "ip-b", NOW), 422, "future"))
ok("a date over a year ago is refused",
   refused(lambda: concerns.submit(form(happened_on="2025-10-01"), "ip-b", NOW), 422, "12 months"))
ok("no date is refused", refused(lambda: concerns.submit(form(happened_on=""), "ip-b", NOW), 422, "date"))
ok("a time that is not hh:mm is refused",
   refused(lambda: concerns.submit(form(happened_time="8am"), "ip-b", NOW), 422, "hh:mm"))
ok("a registration with a symbol is refused",
   refused(lambda: concerns.submit(form(registration="AB12;CD"), "ip-b", NOW), 422, "registration"))
ok("🔴 a pin far from the scheme is refused (Edinburgh)",
   refused(lambda: concerns.submit(form(lat=55.95, lon=-3.19), "ip-b", NOW), 422, "too far"))
ok("no pin and no route is refused",
   refused(lambda: concerns.submit(form(lat=None, lon=None), "ip-b", NOW), 422, "pin"))
ok("a route that is not on the map is refused",
   refused(lambda: concerns.submit(form(lat=None, lon=None, route_id="R999"), "ip-b", NOW), 422, "route"))
ok("a pin that is not a number is refused",
   refused(lambda: concerns.submit(form(lat="north", lon=-0.9), "ip-b", NOW), 422, "pin"))
ok("a reply asked for with no email or phone is refused",
   refused(lambda: concerns.submit(form(wants_reply=True), "ip-b", NOW), 422, "email address or a phone"))
ok("a malformed email is refused",
   refused(lambda: concerns.submit(form(wants_reply=True, email="not-an-address"), "ip-b", NOW), 422, "email"))
ok("nothing refused was stored", concerns.new_count() == 0)

out = concerns.submit(form(wants_reply=True, name="A Reader", email="A.Reader@Example.com", registration="ab12 cde"),
                      "ip-b", NOW)
ok("🔴 the answer is the reference and nothing else", set(out) == {"ok", "ref"} and out["ref"] == "C-0001", str(out))
c1 = concerns.one("C-0001")
ok("the pin is put on the nearest route (R001, within 500 m)", c1["route_id"] == "R001" and c1["route_set_by"] == "pin", str(c1))
ok("the email is kept lower case, the registration upper case",
   c1["email"] == "a.reader@example.com" and c1["registration"] == "AB12 CDE")
ok("it is New, from the public map", c1["status"] == "new" and c1["source"] == "map" and c1["source_text"] == "the public map")
out2 = concerns.submit(form(name="No Reply", email="x@example.com", phone="01234 567890"), "ip-b", NOW)
c2 = concerns.one(out2["ref"])
ok("🔴 no reply asked: the name, email and phone are not stored", c2["name"] is None and c2["email"] is None
   and c2["phone"] is None and c2["wants_reply"] is False, str(c2))
out3 = concerns.submit(form(lat=None, lon=None, route_id="R002", kind="driving"), "ip-b", NOW)
ok("a route picked in the form is kept as the form's", concerns.one(out3["ref"])["route_id"] == "R002"
   and concerns.one(out3["ref"])["route_set_by"] == "form")
hp = concerns.submit(form(website="http://bot"), "ip-c", NOW)
ok("🔴 the trap field: thanked with no reference and nothing stored", hp == {"ok": True, "ref": None}
   and len(concerns.listing()["concerns"]) == 3)
ok("control characters are taken out of the words",
   "\x07" not in concerns.one(concerns.submit(form(words="bell\x07 here"), "ip-d", NOW)["ref"])["words"])

# =========================================================================== #
#  4. The HTTP rules of the public send                                        #
# =========================================================================== #
H = {"X-Wayscope": "1", "Content-Type": "application/json"}
ok("🔴 without the X-Wayscope header: 403",
   refused(lambda: main.concern_public_send(json.dumps(form()).encode(), {"Content-Type": "application/json"}, "9.9.9.1"), 403))
ok("a form-encoded body: 415",
   refused(lambda: main.concern_public_send(b"kind=mud", {"X-Wayscope": "1",
                                                          "Content-Type": "application/x-www-form-urlencoded"}, "9.9.9.1"), 415))
ok("over 8 KB: 413", refused(lambda: main.concern_public_send(b"{" + b" " * 9000 + b"}", H, "9.9.9.1"), 413))
ok("not JSON: 422", refused(lambda: main.concern_public_send(b"{nope", H, "9.9.9.1"), 422))
ok("a JSON list: 422", refused(lambda: main.concern_public_send(b"[1,2]", H, "9.9.9.1"), 422))
ans = main.concern_public_send(json.dumps(form(happened_time="07:00")).encode(), H, "9.9.9.1")
ok("🔴 through the endpoint the answer is still only ok + ref", set(ans) == {"ok", "ref"} and ans["ref"].startswith("C-"))
_aud = db.query("SELECT detail, path, target FROM audit_log WHERE tenant_id = ? AND path = ?",
                (db.current_tenant(), "/api/public/concerns"))
ok("the public send writes one audit row", len(_aud) == 1 and _aud[0]["target"] == ans["ref"], str(_aud))
ok("🔴 the audit row carries no words or contact", "Mud" not in (_aud[0]["detail"] or "")
   and "@" not in (_aud[0]["detail"] or ""))
ok("🔴 the middleware does not copy a concern's body into the log",
   not main._audited("/api/public/concerns") and not main._audited("/api/concerns")
   and not main._audited("/api/concerns/C-0001/reply"))
ok("🔴 the send is behind the map password (not an open path)", gate.scope_for("/api/public/concerns") == "map"
   and "/api/public/concerns" not in gate.OPEN_PATHS)
ok("🔴 /api/concerns is not a map path (the map password never opens it)", gate.scope_for("/api/concerns") is None)

# =========================================================================== #
#  5. The limits                                                               #
# =========================================================================== #
base = len(concerns.listing()["concerns"])
for i in range(5):
    concerns.submit(form(words=f"report {i}"), "ip-flood", NOW)
ok("🔴 the 6th in an hour from one address is refused (429)",
   refused(lambda: concerns.submit(form(), "ip-flood", NOW), 429, "Too many") is not None)
ok("the refusal names the email address when there is one", set_tenant(concern_email="hello@example.org") == []
   and "hello@example.org" in refused(lambda: concerns.submit(form(), "ip-flood", NOW), 429).words)
ok("another address still gets through", concerns.submit(form(), "ip-other", NOW)["ref"])
_later = NOW + datetime.timedelta(hours=2)
for i in range(5):
    concerns.submit(form(words=f"later {i}"), "ip-flood", _later + datetime.timedelta(hours=i))
ok("🔴 more than 20 in a day from one address is refused",
   refused(lambda: concerns.submit(form(), "ip-flood", _later + datetime.timedelta(hours=8)), 429) is not None
   or len(concerns.listing()["concerns"]) - base < 20)
_cap = concerns.PER_TENANT_PER_DAY
concerns.PER_TENANT_PER_DAY = len(concerns.listing()["concerns"])
ok("🔴 the scheme's daily cap refuses everyone",
   refused(lambda: concerns.submit(form(), "ip-fresh", NOW), 429, "busy") is not None)
concerns.PER_TENANT_PER_DAY = _cap

# =========================================================================== #
#  6. Another scheme never sees one                                            #
# =========================================================================== #
mine = len(concerns.listing()["concerns"])
_tok = db.set_current_tenant("other-scheme")
ok("🔴 another scheme's list is empty", concerns.listing()["concerns"] == [] and concerns.new_count() == 0)
ok("🔴 another scheme cannot read C-0001", refused(lambda: concerns.one("C-0001"), 404) is not None)
ok("🔴 another scheme cannot reply to, close or forget C-0001",
   all(refused(f, 404) for f in (lambda: concerns.reply("C-0001", "x", None, "t"), lambda: concerns.close("C-0001", "action", "t"),
                                 lambda: concerns.forget("C-0001", "t"))))
ok("another scheme's export carries none", tenant_package.export_tenant()["tables"]["concerns"] == [])
db._TENANT.reset(_tok)
ok("this scheme still has every one", len(concerns.listing()["concerns"]) == mine and mine > 0)
ok("this scheme's export carries them all", len(tenant_package.export_tenant()["tables"]["concerns"]) == mine)

# =========================================================================== #
#  7. Who may take a staff step                                                #
# =========================================================================== #
access.set_current("submitter123")
ok("🔴 a team code cannot list (403)", refused(lambda: main.concern_list(), 403) is not None)
ok("🔴 a team code cannot read one (403)", refused(lambda: main.concern_one("C-0001"), 403) is not None)
ok("a team code's rail count is 0", main.concern_new_count() == {"new": 0})
access.set_current(None)
ok("🔴 no sign-in: 401", refused(lambda: main.concern_list(), 401) is not None)
ok("no sign-in: the rail count is 0", main.concern_new_count() == {"new": 0})
access.set_current("planner123")
ok("a planner lists them", len(main.concern_list()["concerns"]) == mine)
ok("a planner's rail count is the New ones", main.concern_new_count()["new"] == mine)
ok("the Open filter and the kind filter", len(main.concern_list(status="open")["concerns"]) == mine
   and all(c["kind"] == "driving" for c in main.concern_list(kind="driving")["concerns"])
   and len(main.concern_list(kind="driving")["concerns"]) == 1)
ok("the route filter", all(c["route_id"] == "R002" for c in main.concern_list(route="R002")["concerns"]))
ok("the month filter", len(main.concern_list(month="2026-11")["concerns"]) == mine
   and main.concern_list(month="2026-10")["concerns"] == [])

# =========================================================================== #
#  8. Staff steps                                                              #
# =========================================================================== #
T0 = datetime.datetime(2026, 11, 5, 10, 0, tzinfo=datetime.timezone.utc)
ok("a reply before the concern came in is refused",
   refused(lambda: concerns.reply("C-0001", "Called back", "2026-11-04T09:00:00Z", "Planner", now=T0), 422, "before"))
ok("a reply with no words is refused", refused(lambda: concerns.reply("C-0001", " ", None, "Planner", now=T0), 422))
r = concerns.reply("C-0001", "Phoned 10:30. Sweeper sent.", "2026-11-05T10:30:00Z", "Planner", now=T0 + datetime.timedelta(hours=1))
ok("a reply makes it Answered and starts the KPI clock", r["status"] == "answered"
   and r["first_reply_at"] == "2026-11-05T10:30:00Z" and r["first_reply_days"] == 0.0, str(r))
r = concerns.reply("C-0001", "Wrote again.", "2026-11-06T09:00:00Z", "Planner", now=T0 + datetime.timedelta(days=1))
ok("a later reply keeps the first reply's time", r["first_reply_at"] == "2026-11-05T10:30:00Z"
   and [e["what"] for e in r["history"]].count("reply") == 2)
ok("closing needs a known outcome", refused(lambda: concerns.close("C-0001", "fine", "Planner"), 422) is not None)
r = concerns.close("C-0001", "action", "Planner", now=T0 + datetime.timedelta(days=1))
ok("close sets the outcome and the date", r["status"] == "closed" and r["outcome_text"] == "Our lorry: action taken"
   and r["closed_at"] == "2026-11-06T10:00:00Z")
ok("a reply to a closed one is refused (409)", refused(lambda: concerns.reply("C-0001", "x", None, "P"), 409) is not None)
ok("closing twice is refused (409)", refused(lambda: concerns.close("C-0001", "action", "P"), 409) is not None)
r = concerns.reopen("C-0001", "Planner", now=T0 + datetime.timedelta(days=2))
ok("reopen goes back to Answered (it has a reply)", r["status"] == "answered" and r["outcome"] is None and r["closed_at"] is None)
r = concerns.set_route("C-0001", "R002", "Planner")
ok("staff can move it to another route", r["route_id"] == "R002" and r["route_set_by"] == "staff")
ok("not to a route that is not on the map", refused(lambda: concerns.set_route("C-0001", "R999", "P"), 422) is not None)
_before = concerns.one("C-0001")
r = concerns.forget("C-0001", "Planner")
ok("🔴 Delete the personal details now: contact, words, registration, time and reply notes gone",
   r["name"] is None and r["email"] is None and r["words"] is None and r["registration"] is None
   and r["happened_time"] is None and not any("words" in e for e in r["history"]), str(r))
ok("🔴 ... and the pin rounded to about 100 m", r["lat"] == round(_before["lat"], 3) and r["lon"] == round(_before["lon"], 3))
ok("... the kind, date, route and dates stay", r["kind"] == "mud" and r["happened_on"] == TODAY and r["route_id"] == "R002"
   and r["first_reply_at"])
ok("forgetting twice is refused", refused(lambda: concerns.forget("C-0001", "P"), 409) is not None)
concerns.close("C-0001", "action", "P")
ok("a forgotten one cannot be reopened", refused(lambda: concerns.reopen("C-0001", "P"), 409) is not None)
cid = concerns.add_by_staff({"kind": "noise", "words": "Phoned in: reversing alarms at 06:30.", "happened_on": TODAY,
                             "route_id": "R001", "source": "phone"}, "Planner", now=NOW)
ok("staff add one that came in by phone", concerns.one(cid)["source_text"] == "phone"
   and concerns.one(cid)["history"][0]["what"] == "added from phone")
ok("staff must say how it came in", refused(lambda: concerns.add_by_staff(form(source="map"), "P"), 422, "how it came in"))
_n = db.query("SELECT COUNT(*) AS n FROM audit_log WHERE tenant_id = ? AND path LIKE '/api/concerns/%'", (db.current_tenant(),))
main.concern_close(cid, main.ConcernCloseIn(outcome="no_action"))
_a = db.query("SELECT detail FROM audit_log WHERE tenant_id = ? AND path = ?", (db.current_tenant(), f"/api/concerns/{cid}"))
ok("a staff step writes its own audit row with the step", _a and '"closed"' in _a[-1]["detail"], str(_a))

# =========================================================================== #
#  9. Working days (the KPI clock)                                             #
# =========================================================================== #
ok("Fri 17:00 to Mon 09:00 is 0.7 working days (16 h)", concerns.working_days("2026-11-06T17:00:00Z", "2026-11-09T09:00:00Z") == 0.7)
ok("a whole working week is 5.0", concerns.working_days("2026-11-02T00:00:00Z", "2026-11-09T00:00:00Z") == 5.0)
ok("a weekend alone is 0.0", concerns.working_days("2026-11-07T08:00:00Z", "2026-11-08T20:00:00Z") == 0.0)
ok("a missing end is None", concerns.working_days("2026-11-07T08:00:00Z", None) is None)
ok("add_months clips to the month's end", concerns.add_months(datetime.datetime(2026, 1, 31), 1) == datetime.datetime(2026, 2, 28))
_late = [c for c in concerns.listing(now=NOW)["concerns"] if c["late"]]
ok("nothing is late on the day it came in", _late == [], str(_late[:1]))

# =========================================================================== #
#  10. The clean-up (card 9)                                                   #
# =========================================================================== #


def seed(cid, status, received, closed=None, outcome=None, ip="h"):
    db.execute("INSERT INTO concerns (tenant_id, id, received_at, source, kind, happened_on, happened_time, lat, lon, "
               "words, registration, wants_reply, name, email, phone, ip_hash, status, closed_at, outcome, history_json) "
               "VALUES (?, ?, ?, 'map', 'mud', '2025-01-01', '08:00', 52.612345, -0.912345, 'words', 'AB12CDE', 1, "
               "'N', 'n@example.org', '0123456789', ?, ?, ?, ?, ?)",
               (db.current_tenant(), cid, received, ip, status, closed, outcome,
                json.dumps([{"at": received, "by": "x", "what": "reply", "words": "personal reply note"}])))


SWEEP_NOW = datetime.datetime(2027, 11, 5, 12, 0, tzinfo=datetime.timezone.utc)
seed("C-9001", "closed", "2026-10-01T09:00:00Z", "2026-11-04T09:00:00Z", "action")      # 12 months + 1 day
seed("C-9002", "closed", "2026-10-01T09:00:00Z", "2026-11-06T09:00:00Z", "action")      # 12 months - 1 day
seed("C-9003", "new", "2025-11-04T09:00:00Z")                                            # open, 24 months + 1 day
seed("C-9004", "new", "2025-11-06T09:00:00Z")                                            # open, under 24 months
seed("C-9005", "closed", "2027-09-01T09:00:00Z", "2027-10-05T09:00:00Z", "spam")        # spam, 31 days
seed("C-9006", "closed", "2027-10-01T09:00:00Z", "2027-10-07T09:00:00Z", "spam")        # spam, 29 days
seed("C-9007", "new", "2027-10-30T09:00:00Z")                                            # ip under 30 days
done = concerns.sweep(SWEEP_NOW)
g = {r["id"]: r for r in db.query("SELECT * FROM concerns WHERE tenant_id = ? AND id LIKE 'C-90%'", (db.current_tenant(),))}
ok("🔴 12 months + 1 day after closing: contact, words, registration, time gone", g["C-9001"]["email"] is None
   and g["C-9001"]["words"] is None and g["C-9001"]["registration"] is None and g["C-9001"]["happened_time"] is None
   and g["C-9001"]["personal_deleted_at"], str(g["C-9001"]))
ok("🔴 ... the pin rounded and the reply notes gone", g["C-9001"]["lat"] == 52.612 and g["C-9001"]["lon"] == -0.912
   and "personal reply note" not in g["C-9001"]["history_json"])
ok("... kind, date, status and outcome kept", g["C-9001"]["kind"] == "mud" and g["C-9001"]["outcome"] == "action"
   and g["C-9001"]["happened_on"] == "2025-01-01")
ok("🔴 12 months less a day: everything kept", g["C-9002"]["email"] == "n@example.org" and g["C-9002"]["words"] == "words")
ok("🔴 open 24 months + 1 day: the contact gone, the words kept", g["C-9003"]["email"] is None and g["C-9003"]["name"] is None
   and g["C-9003"]["words"] == "words" and g["C-9003"]["contact_deleted_at"])
ok("open under 24 months: the contact kept", g["C-9004"]["email"] == "n@example.org")
ok("🔴 spam 31 days after closing: the record deleted", "C-9005" not in g)
ok("spam 29 days after closing: kept", "C-9006" in g)
ok("🔴 the hashed address dropped after 30 days, kept before", g["C-9003"]["ip_hash"] is None and g["C-9007"]["ip_hash"] == "h")
ok("the clean-up says what it did", done["spam"] == 1 and done["personal"] >= 1 and done["contact"] == 1, str(done))
ok("running it again changes nothing more", concerns.sweep(SWEEP_NOW) == {"personal": 0, "contact": 0, "spam": 0, "ip": 0})
set_tenant(concern_keep_months=6)
seed("C-9008", "closed", "2027-03-01T09:00:00Z", "2027-05-04T09:00:00Z", "not_ours")    # 6 months + 1 day
concerns.sweep(SWEEP_NOW)
ok("🔴 the client's own months are used (6)", db.query("SELECT email FROM concerns WHERE tenant_id = ? AND id = 'C-9008'",
                                                    (db.current_tenant(),))[0]["email"] is None)
set_tenant(concern_keep_months=12)
concerns._SWEPT.update(at=SWEEP_NOW, tenant=db.current_tenant())
ok("maybe_sweep waits an hour", concerns.maybe_sweep(SWEEP_NOW + datetime.timedelta(minutes=30)) is None
   and concerns.maybe_sweep(SWEEP_NOW + datetime.timedelta(minutes=61)) is not None)
ok("the start-up runs the clean-up", "concerns.maybe_sweep()" in open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read())

# =========================================================================== #
#  11. The alert email (Q7)                                                    #
# =========================================================================== #
_ms = {"DEMO_FROM": "Wayscope <noreply@example.org>", "reply_to": "noreply@example.org"}
msg = concerns.alert_message(out["ref"], _ms)
_body = msg.get_content()
ok("the alert goes to the scheme's report address", msg["To"] == "hello@example.org")
ok("🔴 the alert names the kind, the route and the reference, nothing personal",
   out["ref"] in _body and "Mud or debris" in msg["Subject"] and "a.reader" not in _body.lower()
   and "Mud across" not in _body and "AB12" not in _body, _body)
ok("no alert is built without a report address", set_tenant(concern_email=None) == []
   and concerns.alert_message(out["ref"], _ms) is None)
ok("send_alert without a mail sender returns False and does not raise", concerns.send_alert(out["ref"]) is False)

# =========================================================================== #
#  12. The source                                                              #
# =========================================================================== #
SRC = open(os.path.join(BACKEND, "concerns.py"), encoding="utf-8").read()
MAIN = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
_calls = [SRC[m.end():m.end() + 400] for m in re.finditer(r"db\.(?:query|execute)\(", SRC)]
# NARROWED 5 Nov 2026: the list's one statement is built in `sql` a line above (its filters are optional); that line names
# tenant_id, and is checked here instead of the call
_calls = [c for c in _calls if not c.startswith("sql,")]
ok("🔴 ...the list's statement, built in `sql`, starts from the tenant's rows",
   'sql = f"SELECT {COLS} FROM concerns WHERE tenant_id = ?"' in SRC and SRC.count("db.query(sql,") == 1)
ok("🔴 every statement in concerns.py names tenant_id", len(_calls) >= 10 and all("tenant_id" in c for c in _calls),
   str(len(_calls)))
ok("🔴 no BOOLEAN compared with a number", not re.search(r"\"[^\"\n]*\b(active|disabled|wants_reply|fictional)\s*=\s*[01]\b", SRC))
_pub = re.findall(r'@app\.(get|post|put|patch|delete)\("(/api/public/[^"]*)"\)\s*\n(?:async )?def (\w+)', MAIN)
ok("🔴 the only /api/public/ route that touches concerns is the POST",
   [p for p in _pub if "concern" in p[1] or "concern" in p[2]] == [("post", "/api/public/concerns", "concern_public")], str(_pub))
_reads = [MAIN[MAIN.find(f"def {fn}("):MAIN.find(f"def {fn}(") + 2500] for m, path, fn in _pub if m == "get"]
ok("🔴 no /api/public/ read calls concerns.", all("concerns." not in body.split("\n@app.")[0] for body in _reads))
ok("the staff endpoints all ask for a planner or admin",
   all("_require_approver()" in MAIN[MAIN.find(f"def {fn}("):MAIN.find(f"def {fn}(") + 600]
       for fn in ("concern_list", "concern_one", "concern_add", "concern_reply", "concern_close", "concern_reopen",
                  "concern_route", "concern_forget")))
ok("the seven kinds and six outcomes", len(concerns.KINDS) == 7 and len(concerns.OUTCOMES) == 6)
_BAN = re.compile(r"\b(secure|real-time|AI|optimi[sz]e|predict|telematics|live tracking|truck)\b", re.I)
_words = " ".join(list(concerns.KINDS.values()) + list(concerns.OUTCOMES.values()) +
                  re.findall(r'Refused\(\s*f?"([^"]+)"', SRC))
ok("🔴 no banned public word in what a person reads", not _BAN.search(_words), str(_BAN.findall(_words)))


# =========================================================================== #
#  13. The figures (PR 2: the Dashboard, the bulletin, the CLP)                #
# =========================================================================== #
db.execute("DELETE FROM concerns WHERE tenant_id = ?", (db.current_tenant(),))
OUT1 = network.create_location("Tip North", "origin", lat=52.70, lon=-0.80, loc_type="Quarry", supplies=["aggregate"], receives=["aggregate"])["id"]
OUT2 = network.create_location("Hub South", "destination", lat=52.50, lon=-1.00, loc_type="Compound", supplies=["aggregate"], receives=["aggregate"])["id"]
R3 = network.create_route(OUT1, OUT2, route_id="R003", ipt="IPT1")["id"]


def seed2(cid, received, kind="mud", route=None, status="new", first=None, closed=None, outcome=None, wants=1, loc=None):
    db.execute("INSERT INTO concerns (tenant_id, id, received_at, source, kind, happened_on, lat, lon, route_id, location_id, "
               "words, wants_reply, name, email, status, first_reply_at, closed_at, outcome, history_json) "
               "VALUES (?, ?, ?, 'map', ?, '2026-10-01', 52.6, -0.9, ?, ?, 'Secret words here', ?, 'Secret Name', "
               "'secret@example.org', ?, ?, ?, ?, '[]')",
               (db.current_tenant(), cid, received, kind, route, loc, wants, status, first, closed, outcome))


# Mon 5 Oct 2026 09:00 is the clock's start; a reply at 09:00 on Tue is 1.0 working day, on Mon 12th 5.0
seed2("C-0101", "2026-10-05T09:00:00Z", "mud", R1, "closed", "2026-10-06T09:00:00Z", "2026-10-07T09:00:00Z", "action")
seed2("C-0102", "2026-10-05T09:00:00Z", "mud", R2, "closed", "2026-10-13T09:00:00Z", "2026-10-14T09:00:00Z", "no_action")
seed2("C-0103", "2026-10-05T09:00:00Z", "driving", R1, "answered", "2026-10-05T21:00:00Z")
seed2("C-0104", "2026-09-07T09:00:00Z", "noise", R3, "closed", "2026-09-08T09:00:00Z", "2026-10-02T09:00:00Z", "not_ours")
seed2("C-0105", "2026-10-05T09:00:00Z", "other", R1, "closed", None, "2026-10-05T10:00:00Z", "spam")   # never counted
seed2("C-0106", "2026-10-20T09:00:00Z", "parked", None, "new", wants=1, loc=YARD)                       # pinned at the yard
seed2("C-0107", "2026-08-03T09:00:00Z", "mud", R1, "new", wants=0)                                      # outside the range
set_tenant(concerns_on=True, concern_reply_days=5, concern_email="team@example.org")
FNOW = datetime.datetime(2026, 11, 5, 9, 0, tzinfo=datetime.timezone.utc)
F = concerns.figures("2026-09", "2026-10", now=FNOW)
ok("⭐ FIGURES: received in the range, 'Not a concern' never counted", F["received"] == 5, str(F["received"]))
ok("FIGURES: a month for every month of the range, in order", [m["month"] for m in F["by_month"]] == ["2026-09", "2026-10"]
   and [m["received"] for m in F["by_month"]] == [1, 4], str(F["by_month"]))
ok("FIGURES: closed counts the closings in the range; open now counts every open one (the range does not narrow it)",
   F["closed"] == 3 and F["open_now"] == 3 and F["closed_of_received"] == 3, f'{F["closed"]} {F["open_now"]}')
ok("FIGURES: the medians in working days (first reply 1.0, 5.0, 0.5, 1.0 → 1.0; close 2.0, 7.0, 19.0 → 7.0)",
   F["first_reply_median"] == 1.0 and F["close_median"] == 7.0, f'{F["first_reply_median"]} {F["close_median"]}')
ok("FIGURES: replied within the target (5 working days): 3 of the 5 that asked and are due (C-0102 took 6; C-0106 has waited past 5 with none)",
   F["within"] == {"n": 5, "yes": 3, "pct": 60}, str(F["within"]))
ok("FIGURES: by kind, the busiest first, with how many are closed",
   [(k["kind"], k["received"], k["closed"]) for k in F["by_kind"]][:2] == [("mud", 2, 2), ("driving", 1, 0)]
   and {k["kind"] for k in F["by_kind"]} == {"mud", "driving", "noise", "parked"}, str(F["by_kind"]))
ok("FIGURES: the busiest routes, at most five, with their words",
   [(r["route_id"], r["received"]) for r in F["routes"]] == [("R001", 2), ("R002", 1), ("R003", 1)]
   and F["routes"][0]["words"] == "Pit West → Yard East", str(F["routes"]))
ok("🔴 FIGURES: counts only — no words, name, email or place in the answer",
   not any(w in json.dumps(F) for w in ("Secret words", "Secret Name", "secret@example.org", "52.6", "-0.9")))
FS = concerns.figures("2026-09", "2026-10", sites=[YARD], now=FNOW)
ok("⭐ FIGURES (Sites): a site keeps the routes that start or end there and the concerns pinned there",
   FS["received"] == 4 and all(r["route_id"] != "R003" for r in FS["routes"]), str(FS["received"]))
ok("FIGURES (Sites): a site with no route and no pin has none", concerns.figures("2026-09", "2026-10", sites=["L999"])["received"] == 0)
ok("FIGURES: no reply target, no 'within' figure", set_tenant(concern_reply_days=None) == []
   and concerns.figures("2026-09", "2026-10")["within"] is None)
set_tenant(concern_reply_days=5)
ok("🔴 FIGURES: a bad range is refused in words", refused(lambda: concerns.figures("2026-10", "2026-09"))
   and refused(lambda: concerns.figures("Oct", "2026-10")))
_fig = MAIN[MAIN.find("def concern_figures("):MAIN.find("def concern_figures(") + 700]
ok("🔴 FIGURES: the endpoint asks for a planner or admin and is matched before /api/concerns/{cid}",
   "_require_approver()" in _fig and 0 < MAIN.find('"/api/concerns/figures"') < MAIN.find('"/api/concerns/{cid}"'))
ok("FIGURES: read fresh, never kept (no read_cache / _staff_json on it)",
   "_staff_json" not in _fig and "read_cache" not in _fig)

# the bulletin's glance row and short table (card 7)
import bulletin_doc  # noqa: E402
_cm = bulletin_doc.concern_month(10)            # October 2026
# REVERSED 11 Nov 2026 (card A-F1): "closed" counts October's concerns that are closed now (2: C-0101, C-0102), the same
# count as the kinds table; C-0104 (received in September, closed in October) is no longer in it. It read 3.
ok("⭐ BULLETIN: October's concerns — received, closed (of those received), by kind, the median first reply",
   _cm is not None and _cm["received"] == 4 and _cm["closed"] == 2 and _cm["kinds"][0] == {"kind": "Mud or debris on the road", "received": 2, "closed": 2},
   str(_cm))
_g = bulletin_doc._glance({}, {}, [], [], [], None, [], None, "October 2026", _cm)
# NARROWED 5 Nov 2026 (the newsletter stays at four pages, D43): the item carries "received · closed", the figure only the two
# counts, the data cell a short "Map and email records", so no cell wraps in the PDF's narrow columns
# REVERSED 11 Nov 2026 (card A-F1): "4 · 2", the kinds table's own sums (it read "4 · 3", one more closed than the table)
ok("BULLETIN: the glance row reads 'Concerns from the public, received · closed: 4 · 2', marked as a record",
   any(r["item"] == "Concerns from the public, received · closed" and r["figure"] == "4 · 2" and not r["not_reported"]
       and r["data"] == "Map and email records" for r in _g), str(_g[-1]))
ok("BULLETIN: ...each cell short enough for one line in the PDF (figure ≤ 12 characters like 'Not reported', data ≤ 22)",
   all(len(r["figure"]) <= 12 and len(r["data"]) <= 22 for r in _g if r["item"].startswith("Concerns")))
ok("⭐ BULLETIN (A-F1): the glance row's closed figure equals the kinds table's closed, summed",
   _cm["closed"] == sum(k["closed"] for k in _cm["kinds"]) and _cm["received"] == sum(k["received"] for k in _cm["kinds"]),
   str(_cm))
ok("BULLETIN (A-F1): the form is on here, and the row says so", _cm["form"] is True)
_gx = bulletin_doc._glance({}, {}, [], [], [], None, [], None, "October 2026", dict(_cm, form=False))
ok("⭐ BULLETIN (A-F1): with the map's form off the row's source is 'Email records', never the map",
   any(r["item"].startswith("Concerns") and r["data"] == "Email records" for r in _gx)
   and not any("Map and email" in r["data"] for r in _gx), str(_gx[-1]))
_g0 = bulletin_doc._glance({}, {}, [], [], [], None, [], None, "October 2026", None)
ok("BULLETIN: ...and without concerns it is still 'Enquiries and complaints: Not reported'",
   _g0[-1] == {"item": "Enquiries and complaints", "figure": "Not reported", "data": "Not in this bulletin", "not_reported": True})
ok("BULLETIN: the line under the table", bulletin_doc.concern_reply_line(_cm) == "First reply: median 1 working day."
   and bulletin_doc.concern_reply_line({"first_reply_median": 2.5}) == "First reply: median 2.5 working days."
   and bulletin_doc.concern_reply_line({}) == "")
ok("🔴 BULLETIN: counts only — no words, name or email", not any(w in json.dumps(_cm) for w in ("Secret", "secret@")))
_EXP = open(os.path.join(BACKEND, "export.py"), encoding="utf-8").read()
_GLF = _EXP[_EXP.index("def _glance_flow(K, S):"):_EXP.index("def _lot_flow(")]
ok("BULLETIN (paper): the concerns are the glance row only — no table and no line of kinds in the PDF (the newsletter stays at four pages, D43)",
   "LongTable(ck" not in _EXP and "concern_kinds_line" not in _EXP and 'S.get("concerns")' not in _GLF)

db.execute("DELETE FROM concerns WHERE tenant_id = ? AND id LIKE 'C-01%'", (db.current_tenant(),))
set_tenant(concerns_on=False)
ok("BULLETIN: a scheme with no form and none recorded keeps the row Not reported", bulletin_doc.concern_month(10) is None)

# the CLP's section 7 paragraph (card 7)
import clp_doc  # noqa: E402
seed2("C-0201", "2026-06-01T09:00:00Z", "mud", R1, "closed", "2026-06-02T09:00:00Z", "2026-06-03T09:00:00Z", "action")
seed2("C-0202", "2026-10-01T09:00:00Z", "mud", R3, "closed", "2026-10-02T09:00:00Z", "2026-10-03T09:00:00Z", "action")
seed2("C-0203", "2025-10-01T09:00:00Z", "mud", R1, "closed", "2025-10-02T09:00:00Z", "2025-10-03T09:00:00Z", "action")
_d = {"snapshot": datetime.datetime(2026, 11, 5, 9, 0), "location_ids": [YARD], "name": "Yard East"}
set_tenant(concerns_on=True, concern_reply_days=5, concern_email="team@example.org")
_cw = clp_doc.concern_words(_d)
ok("⭐ CLP §7: how concerns are taken (map and email), the reply target, the 12 months' counts for the sites' routes",
   _cw == ("Concerns from the public are taken on the scheme's public map (Report a concern) and by email to team@example.org. "
           "Each gets a reference, a first reply within 5 working days where the person left a way to reach them, and is "
           "closed with an outcome. In the 12 months to November 2026, on the routes to and from Yard East: 1 received, "
           "1 closed, median first reply 1 working day."), _cw)
set_tenant(concerns_on=False)
ok("CLP §7: email only", clp_doc.concern_words(_d).startswith("Concerns from the public are taken by email to team@example.org."))
set_tenant(concern_email=None)
ok("CLP §7: no way in → None (the To complete line stays)", clp_doc.concern_words(_d) is None)
_CLPSRC = open(os.path.join(BACKEND, "clp_doc.py"), encoding="utf-8").read()
ok("CLP §7: the paragraph replaces only the complaints part of the To complete line",
   'D.todo("how this plan is put in place on site, who checks it and how often, and when the plan is reviewed.", "7")' in _CLPSRC
   and "how complaints are taken and answered" in _CLPSRC)
set_tenant(concerns_on=True, concern_email="team@example.org")
db.execute("DELETE FROM concerns WHERE tenant_id = ? AND id LIKE 'C-02%'", (db.current_tenant(),))

print()
for f in FAIL:
    print("  FAIL:", f)
print(f"\ntest_concerns: {PASS} passed, {len(FAIL)} failed")
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
