"""
23 Oct 2026 — the Teams tab (backend/teams.py, /api/admin/teams*) and the team WORDS fixed on the same branch
(`claude/team-words`). John: the limit stays six teams; admins only add one.

Run from the repo root:  python backend/tests/test_teams.py

What this proves, on a scratch SQLite database (FastAPI stubbed, so the endpoint bodies run as plain functions):
  1. words: an unnamed team reads "<team word> n", never its id, also once six team rows exist (the old
     six-row shortcut skipped the tenant's word); team_labels() carries named rows only; a wrong team on a line is
     "That team is not set up here." (no id, no range); the limit is six, read from access.IPT_IDS.
  2. the Teams API: listing by NAME in number order with logins and lines; add takes the lowest slot never used
     (not one a forecast line or a login carries), refuses a seventh, a duplicate name (any case, stopped teams
     included), an id-like name, an empty or 61-character name; rename; stop refused while a login can sign in,
     allowed once it cannot, the stopped slot never handed out again; use again; a stopped team leaves the pickers
     (/api/meta ipts, the Users picker, access.tenant_team_ids) but keeps its name on its lines; a planner login,
     a team login and no token are all refused (403); an admin login passes without the token.
  3. the Users endpoints refuse a login into a stopped or non-existent team.

What it does not prove: the HTTP layer and the audit row (http_smoke.py), the page itself (dom_frontend.js,
parse_frontend.js), Postgres (two admins adding at once: the primary key refuses the second; not run here).
"""
import datetime
import os
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


# --------------------------------------------------------------------------- the FastAPI stub (as test_users.py)
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

    def set_cookie(self, **kw):
        pass

    def delete_cookie(self, key, **kw):
        pass


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


_stbg.BackgroundTask = _BackgroundTask
_st.background = _stbg
sys.modules.setdefault("starlette", _st)
sys.modules.setdefault("starlette.background", _stbg)

TMP = tempfile.mkdtemp(prefix="wayscope_teams_")
from portable import remove_scratch_db   # noqa: E402  tests/portable.py
for v in ("DATABASE_URL", "SMTP_USER", "SMTP_PASSWORD", "DEMO_FROM", "DEMO_NOTIFY", "LANDING_URL", "APP_URL",
          "DEMO_TEAM_CODE_VAR", "DEMO_REPLY_TO", "ALLOW_DEMO_CODES", "MAP_GATE", "TENANT_ID", "IPT1_CODE",
          "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE", "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(v, None)
os.environ.update({"ADMIN_TOKEN": "adm-token-for-tests", "MAP_PASSWORD": "map-pass-abc",
                   "GATE_SECRET": "gate-secret-for-tests"})

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import access  # noqa: E402
import config  # noqa: E402
import conversions  # noqa: E402
import network  # noqa: E402
import taxonomy  # noqa: E402
import teams  # noqa: E402
import users  # noqa: E402
import main  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def status_of(fn):
    """The HTTPException status fn raises, else 200."""
    try:
        fn()
    except _HTTPException as e:
        return e.status_code
    return 200


def detail_of(fn):
    try:
        fn()
    except _HTTPException as e:
        return e.detail
    return None


T = db.current_tenant
users.NOW = datetime.datetime(2026, 10, 23, 9, 0, tzinfo=datetime.timezone.utc)
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_config_db(); db.init_demo_requests_db(); db.init_users_db()
for i, lab in (("IPT1", "North Team"), ("IPT2", "Central Team"), ("IPT3", "South Team")):
    db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (T(), i, lab, True))

ADMIN = {"role": "admin", "ipt": None, "label": "Admin", "via": "login", "user_id": "u-admin", "name": "Ada Admin",
         "email": "ada@example.org", "kind": "staff"}
PLANNER = {"role": "planner", "ipt": None, "label": "Planner", "via": "login", "user_id": "u-plan", "name": "Pat Plan",
           "email": "pat@example.org", "kind": "staff"}
TEAMLOGIN = {"role": "ipt", "ipt": "IPT1", "label": "North Team", "via": "login", "user_id": "u-n", "name": "Nia North",
             "email": "nia@example.org", "kind": "staff"}


def as_(acc):
    return access._ACCESS.set(acc)


# =========================================================================== #
#  1. words                                                                    #
# =========================================================================== #
ok("the limit is six, read from access.IPT_IDS", teams.limit() == 6 == len(access.IPT_IDS))
ok("team_labels() carries the named rows only", taxonomy.team_labels() == {"IPT1": "North Team", "IPT2": "Central Team",
                                                                            "IPT3": "South Team"}, str(taxonomy.team_labels()))
db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (T(), "IPT4", "", True))
db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (T(), "IPT5", None, True))
ok("🔴 a team row with an empty name reads 'Team 4', never 'IPT4' (it used to fall back to the id)",
   taxonomy.team_name("IPT4") == "Team 4" and taxonomy.team_text("IPT4 / IPT1") == "Team 4 / North Team",
   taxonomy.team_name("IPT4") + " | " + str(taxonomy.team_text("IPT4 / IPT1")))
ok("...and a NULL name too", taxonomy.team_name("IPT5") == "Team 5", taxonomy.team_name("IPT5"))
ok("...and team_labels() still holds only the named rows", "IPT4" not in taxonomy.team_labels()
   and "IPT5" not in taxonomy.team_labels())
db.execute("INSERT INTO ipts (tenant_id, id, label, active) VALUES (?, ?, ?, ?)", (T(), "IPT6", None, True))
_doc = config.load(conversions, use_cache=False)
_doc["tenant"]["team_label"] = "Contractor"
config.save(_doc, by="test", network=network); config.invalidate()
ok("🔴 with SIX team rows the tenant's word is still used for an unnamed one (the six-row shortcut is gone)",
   taxonomy.team_text("IPT6") == "Contractor 6" and taxonomy.team_name("IPT6") == "Contractor 6",
   str(taxonomy.team_text("IPT6")))
ok("...and a named team is still its name", taxonomy.team_text("IPT2") == "Central Team")
_doc["tenant"]["team_label"] = "Team"
config.save(_doc, by="test", network=network); config.invalidate()
db.execute("DELETE FROM ipts WHERE tenant_id = ? AND id IN ('IPT4', 'IPT5', 'IPT6')", (T(),))

_tok = as_(PLANNER)
_ipt, _err = access.ipt_for_save("IPT7")
ok("🔴 a wrong team on a line: 'That team is not set up here.' (no id, no range)",
   _ipt is None and _err == "That team is not set up here.", str(_err))
ok("...the six slots still save", access.ipt_for_save("IPT6") == ("IPT6", None))
access._ACCESS.reset(_tok)
ok("the old message is gone from access.py", "is not one of IPT1..IPT6" not in open(os.path.join(BACKEND, "access.py"),
                                                                                      encoding="utf-8").read())

# =========================================================================== #
#  2. the Teams API                                                            #
# =========================================================================== #
TOKEN = "adm-token-for-tests"
L = main.admin_teams(TOKEN)
ok("listing: three teams by NAME, in number order, with room for three more",
   [t["label"] for t in L["teams"]] == ["North Team", "Central Team", "South Team"] and L["used"] == 3
   and L["max"] == 6 and L["can_add"] is True, str(L)[:200])
ok("...no label in the listing is a slot id", all(not access.canonical_ipt(t["label"]) for t in L["teams"]))

# a login and a line, so the counts mean something
_u, _e = users.create_user("nia@example.org", "Nia North", "team", "IPT1", created_by="test")
db.execute("UPDATE users SET password_hash = ? WHERE tenant_id = ? AND id = ?", ("x", T(), _u["id"]))
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, status, ipt) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (T(), "F1", "R1", 10, "earthworks", "WS1", 100, "t", "Approved", "IPT1"))
# a forecast line carrying slot 4 though no team row has it (a package's leftover): slot 4 is NOT free
db.execute("INSERT INTO forecasts (tenant_id, id, route_id, month_index, discipline, section_id, quantity, unit, status, ipt) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (T(), "F2", "R1", 11, "earthworks", "WS1", 50, "t", "Approved", "IPT 4"))
L = main.admin_teams(TOKEN)
_n = {t["label"]: t for t in L["teams"]}
ok("listing: North Team has 1 login and 1 line", _n["North Team"]["logins"] == 1 and _n["North Team"]["lines"] == 1, str(_n["North Team"]))

r = main.admin_team_add(main.TeamIn(label="  Drainage package "), TOKEN)
ok("🔴 add: the lowest slot NEVER used (IPT5: a forecast line already carries IPT4)",
   r["team"]["id"] == "IPT5" and r["team"]["label"] == "Drainage package", str(r["team"]))
ok("...the answer carries the new listing", [t["label"] for t in r["teams"]][-1] == "Drainage package")
_tok = as_(PLANNER)
ok("...and it is in /api/meta's team pickers and the Users picker at once",
   "IPT5" in [i["id"] for i in main.meta()["ipts"]] and "IPT5" in [t["id"] for t in main._teams()], str(main.meta().get("ipts"))[:200])
access._ACCESS.reset(_tok)
ok("...and in access.tenant_team_ids()", "IPT5" in access.tenant_team_ids(), str(access.tenant_team_ids()))
ok("add: a duplicate name is refused, any case", status_of(lambda: main.admin_team_add(main.TeamIn(label="north team"), TOKEN)) == 400)
ok("add: an id-like name is refused", status_of(lambda: main.admin_team_add(main.TeamIn(label="IPT 6"), TOKEN)) == 400)
ok("add: an empty or 61-character name is refused",
   status_of(lambda: main.admin_team_add(main.TeamIn(label="   "), TOKEN)) == 400
   and status_of(lambda: main.admin_team_add(main.TeamIn(label="x" * 61), TOKEN)) == 400
   and status_of(lambda: main.admin_team_add(main.TeamIn(label="x" * 60), TOKEN)) == 200)
L = main.admin_teams(TOKEN)
ok("🔴 after two adds (IPT5, IPT6) the organisation is full with five teams: slot 4 stays spoken for by its line",
   L["used"] == 5 and [t["id"] for t in L["teams"]][-2:] == ["IPT5", "IPT6"] and "IPT4" not in [t["id"] for t in L["teams"]]
   and L["can_add"] is False and teams.next_slot() is None, str([t["id"] for t in L["teams"]]))
_d = detail_of(lambda: main.admin_team_add(main.TeamIn(label="Signals"), TOKEN))
ok("🔴 no seventh slot: refused with words a person reads", _d == "All 6 team places are used.", str(_d))
main.admin_team_change("IPT6", main.TeamPatch(label="Bridges package"), TOKEN)

# rename
r = main.admin_team_change("IPT2", main.TeamPatch(label="Central Civils"), TOKEN)
ok("rename: the name changes everywhere team words are read", r["team"]["label"] == "Central Civils"
   and taxonomy.team_name("IPT2") == "Central Civils" and taxonomy.team_text("IPT2 / IPT1") == "Central Civils / North Team")
ok("rename: to another team's name is refused", status_of(lambda: main.admin_team_change("IPT2", main.TeamPatch(label="South Team"), TOKEN)) == 400)
ok("rename: to its own name in another case is allowed", status_of(lambda: main.admin_team_change("IPT2", main.TeamPatch(label="CENTRAL CIVILS"), TOKEN)) == 200)
main.admin_team_change("IPT2", main.TeamPatch(label="Central Civils"), TOKEN)
ok("an unknown team is 404", status_of(lambda: main.admin_team_change("IPT9", main.TeamPatch(label="Ghost"), TOKEN)) == 404)

# stop and resume
_d = detail_of(lambda: main.admin_team_change("IPT1", main.TeamPatch(active=False), TOKEN))
ok("🔴 stop: refused while a login of the team can sign in", _d == "Move or disable its 1 login first.", str(_d))
users.update_user(_u["id"], {"disabled": True})
r = main.admin_team_change("IPT1", main.TeamPatch(active=False), TOKEN)
ok("stop: allowed once no login can sign in", r["team"]["active"] is False)
ok("🔴 a stopped team leaves the pickers", "IPT1" not in access.tenant_team_ids()
   and "IPT1" not in [t["id"] for t in main._teams()])
ok("...but keeps its NAME on its lines", taxonomy.team_name("IPT1") == "North Team"
   and taxonomy.team_text("IPT1") == "North Team")
L = main.admin_teams(TOKEN)
ok("...and stays in the Teams tab, stopped, still counted", any(t["id"] == "IPT1" and not t["active"] for t in L["teams"])
   and L["used"] == 5 and L["can_add"] is False)
ok("🔴 a login cannot be put in a stopped team",
   status_of(lambda: main.admin_user_add(main.UserIn(email="new@example.org", name="New Person", role="team", team="IPT1"), TOKEN)) == 400)
ok("...nor in a slot the organisation has no team for",
   status_of(lambda: main.admin_user_add(main.UserIn(email="new2@example.org", name="New Person", role="team", team="IPT4"), TOKEN)) == 400)
_b, _be = users.create_user("bo@example.org", "Bo Bridge", "team", "IPT6", created_by="test")
ok("...nor moved into one", status_of(lambda: main.admin_user_change(_b["id"], main.UserPatch(role="team", team="IPT1"), TOKEN)) == 400)
ok("...while an active team still takes a login",
   status_of(lambda: main.admin_user_add(main.UserIn(email="new3@example.org", name="New Person", role="team", team="IPT6"), TOKEN)) == 200)
r = main.admin_team_change("IPT1", main.TeamPatch(active=True), TOKEN)
ok("use again: back in the pickers", r["team"]["active"] is True and "IPT1" in access.tenant_team_ids())

# who may
_tok = as_(PLANNER)
ok("🔴 a planner login is refused (admins only, John 23 Oct)", status_of(lambda: main.admin_teams(None)) == 403
   and status_of(lambda: main.admin_team_add(main.TeamIn(label="Planner's team"), None)) == 403)
access._ACCESS.reset(_tok)
_tok = as_(TEAMLOGIN)
ok("a team login is refused", status_of(lambda: main.admin_team_change("IPT1", main.TeamPatch(label="Ours"), None)) == 403)
access._ACCESS.reset(_tok)
ok("no token, nobody signed in: refused", status_of(lambda: main.admin_teams(None)) == 403)
_tok = as_(ADMIN)
ok("an admin login passes without the token", status_of(lambda: main.admin_teams(None)) == 200)
access._ACCESS.reset(_tok)

print(f"\ntest_teams: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
remove_scratch_db(db, TMP)
sys.exit(1 if FAIL else 0)
