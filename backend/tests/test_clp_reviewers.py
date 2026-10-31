"""
The contractor's CLIENT reviewers, 31 Oct 2026 (task 4a, PR 3c) — backend/clp_reviews.py, the reviewer logins in users.py,
the separate reviewer context in access.py, and the /api/admin/reviewer*, /api/clp/documents/{id}/review-send and
/api/review/* endpoints. Mockup notes/clp-reviewers-mockup-1031/ (Q1–Q12, all as recommended).

What is asserted: the groups (add, rename, stop — which signs its reviewers out — start again, delete only when nothing was
sent and nobody is in it); a reviewer login (kind 'reviewer', a group, role 'reviewer', no team, never a code, two-step from
the first sign-in, an end date, stopped by its group); 🔴 THE WALL — a reviewer's session never resolves to an access dict
(access.current() is None, every staff guard and helper refuses it), the review reads look a CLP up only through the
group's sends (another group's CLP, a draft, an issue never sent: all a 404), a reviewer visit builds nothing; sending
(planners and admins, issued CLPs only, a group skipped when it already has the issue, the approve card's ticks); the
decision (one per group per issue, the first stands, another reviewer changes it while the issue is the latest, all kept,
a newer issue starts fresh, Returned needs words); the notes (a reviewer's comment with its group, never deleted by the
contractor, Make a task from it; a contractor note reaches a group only when shown to it; tasks never); the two emails;
the audit trail; the contractor's list lines; the Document history's group lines; the organisation file; the demo group.

WHAT THIS DOES NOT PROVE
------------------------
  * The HTTP layer is stubbed here. smoke_reviewer_wall.py drives the REAL app: every /api route as a reviewer, with a
    real two-step sign-in and the session cookie.
  * SQLite only; the emails are captured, never sent.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_clp_reviewers.py
"""
import base64
import copy
import io
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

# ---- stubs, as test_clp_notes.py ----------------------------------------------------
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
    def __init__(self, status_code, detail="", headers=None):
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


class _Request:
    def __init__(self, headers=None, cookies=None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.cookies = dict(cookies or {})
        self.client = None
        self.query_params = {}


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


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="rbe_clprev_")
from portable import remove_scratch_db, offline   # noqa: E402  tests/portable.py
os.environ.pop("DATABASE_URL", None)
os.environ.pop("ADMIN_TOKEN", None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import days  # noqa: E402
import costing  # noqa: E402
import config  # noqa: E402
import gates  # noqa: E402
import network  # noqa: E402
import taxonomy  # noqa: E402
import carbon_target  # noqa: E402
import clp_doc  # noqa: E402
import export  # noqa: E402
offline(export)
for _v in ("IPT1_CODE", "IPT2_CODE", "IPT3_CODE", "IPT4_CODE", "IPT5_CODE", "IPT6_CODE",
           "PLANNER_CODE", "ADMIN_CODE"):
    os.environ.pop(_v, None)
os.environ["ALLOW_DEMO_CODES"] = "1"
days.START_YEAR = main.START_YEAR

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def _raises(fn):
    try:
        fn()
    except Exception as e:
        return e
    return None


def status_of(fn):
    e = _raises(fn)
    return getattr(e, "status_code", None) if e else 200


ART = network.DEFAULT_PROFILE
BAL = "Large aggregate / ballast"

# =========================================================================== #
#  0. A small scheme: one compound with approved lorries for two teams        #
# =========================================================================== #
remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
db.init_tenant()
db.init_users_db()
taxonomy.seed_taxonomy()
config.invalidate()
config.seed_from_file(conversions)
config.invalidate()
costing.invalidate()
carbon_target.invalidate()
access.set_current("planner123")
_doc = copy.deepcopy(config.load(conversions, use_cache=False))
_doc.setdefault("tenant", {})["demo_notice"] = "Fictional scheme"
_doc["tenant"]["name"] = "Test contractor"
config.save(_doc, by="tester")
config.invalidate()
factors = conversions.load_factors()

PIT = network.create_location("Pit West", "origin", lat=52.55, lon=-0.95, loc_type="Quarry", supplies=[BAL])["id"]
YARD = network.create_location("Yard East", "destination", lat=52.6447, lon=-0.8822, loc_type="Compound", receives=[BAL])["id"]
PILE = network.create_location("Pile North", "destination", lat=52.58, lon=-0.92, loc_type="Stockpile", receives=[BAL])["id"]
R_IN = network.create_route(PIT, YARD, material_category=BAL, route_id="R001", ipt="IPT1")["id"]
R_PILE = network.create_route(PIT, PILE, material_category=BAL, route_id="R002", ipt="IPT2")["id"]
for _rid in (R_IN, R_PILE):
    for _leg in ("loaded", "return"):
        db.execute("INSERT INTO route_geometry (tenant_id, route_id, vehicle_profile, leg, alt_index, geometry, distance_km, "
                   "duration_hr, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (db.current_tenant(), _rid, ART, _leg, 0, "[]", 20.0, 0.5, "2026-10-30T00:00:00Z"))


def _line(rid, disc, sect, month, ipt):
    main.save_matrix_row(main.MatrixRow(
        route_id=rid, discipline=disc, section_id=sect, material_type=BAL, material_description=None,
        vehicle_type=ART, submitted_by="tester", unit="t", status="Pending",
        cells=[main.Cell(month_index=m, quantity=q) for m, q in month], ipt=ipt))
    main.set_route_status(rid, main.StatusUpdate(status="Approved"), discipline=disc, section_id=sect)


_line(R_IN, "substructure", "WS1", [(10, 2900.0), (11, 5800.0)], "IPT1")
_line(R_PILE, "substructure", "WS2", [(10, 2900.0)], "IPT2")
gates.create_gate(YARD, "Yard gate", 52.6447, -0.8822, direction="both", is_default=True)
for _tid, _lab in (("IPT1", "North Team"), ("IPT2", "Central Team")):
    db.execute("INSERT INTO ipts (tenant_id, id, label, manager, active, merged_into) VALUES (?, ?, ?, ?, ?, ?)",
               (db.current_tenant(), _tid, _lab, None, True, None))
config.invalidate()
factors = conversions.load_factors()

import clp_records  # noqa: E402
import clp_notes  # noqa: E402
import clp_reviews  # noqa: E402
import tenant_package  # noqa: E402
import users  # noqa: E402
import demo_request  # noqa: E402

SENT = []
users.mail_settings = lambda: {"DEMO_FROM": "Wayscope <hello@example.com>", "reply_to": "hello@example.com"}
demo_request.send = lambda msg, settings: SENT.append(msg)


def login(email, name, role, team=None, kind="staff"):
    u, err = users.create_user(email, name, role, team=team, kind=kind)
    assert u, err
    return u


U_PAT = login("pat@example.com", "Pat Planner", "planner")
U_ADA = login("ada@example.com", "Ada Admin", "admin")
U_NORA = login("nora@example.com", "Nora North", "team", "IPT1")
PAT = users.access_for(users.get_user(U_PAT["id"]))
ADA = users.access_for(users.get_user(U_ADA["id"]))
NORA = users.access_for(users.get_user(U_NORA["id"]))


def as_(acc):
    access._ACCESS.set(acc)
    access._REVIEWER.set(None)


def as_rev(rev):
    access._ACCESS.set(None)
    access._REVIEWER.set(rev)


def build_fast(data, rec):
    return clp_doc.build(data, impact=rec["impact"], pictures=False)


Y_ALL = clp_records.auto_id(YARD, None)
Y_N = clp_records.auto_id(YARD, "IPT1")
P_ALL = clp_records.auto_id(PILE, None)

# =========================================================================== #
#  1. Groups (admins)                                                          #
# =========================================================================== #
as_(ADA)
NH, err = clp_reviews.add_group("National Highways", "Ada Admin")
ok("1. an admin adds a group", NH and not err and NH["id"].startswith("rg-"), str(err))
HDC, _e = clp_reviews.add_group("Harborough District Council", "Ada Admin")
ok("1. a second group", HDC is not None)
_d, err = clp_reviews.add_group("  national highways ", "Ada Admin")
ok("1. 🔴 a duplicate name (any case) is refused in words", _d is None and err == "There is already a group with that name.", str(err))
ok("1. an empty name is refused", clp_reviews.add_group("", "x")[1] == "Enter the organisation's name.")
ok("1. the listing has both, in name order, with no reviewers yet",
   [g["name"] for g in clp_reviews.listing()["groups"]] == ["Harborough District Council", "National Highways"]
   and all(g["reviewers"] == 0 and g["can_delete"] for g in clp_reviews.listing()["groups"]))
ok("1. 🔴 the Client reviewers endpoints are admins only (a planner login is refused)",
   (as_(PAT) or True) and status_of(lambda: main.admin_reviewers(None)) == 403
   and status_of(lambda: main.admin_review_group_add(main.ReviewGroupIn(name="X"), None)) == 403)
as_(ADA)
_tmp, _ = clp_reviews.add_group("Temporary client", "Ada Admin")
ok("1. a group nothing went to and nobody is in can be deleted", clp_reviews.delete_group(_tmp["id"]) is None
   and _tmp["id"] not in clp_reviews.group_names())

# =========================================================================== #
#  2. Reviewer logins                                                          #
# =========================================================================== #
SAM, err = clp_reviews.add_reviewer("sam.reviewer@example.org", "Sam Reviewer", NH["id"], by="Ada Admin")
ok("2. an admin adds a reviewer in a group", SAM and not err, str(err))
ok("2. 🔴 a reviewer login: kind reviewer, role reviewer, NO team, its group",
   SAM["kind"] == "reviewer" and SAM["role"] == "reviewer" and not SAM.get("team") and SAM["review_group"] == NH["id"])
ALEX, _ = clp_reviews.add_reviewer("alex@example.org", "Alex Example", NH["id"], by="Ada Admin")
HAL, _ = clp_reviews.add_reviewer("hal@example.org", "Hal Harborough", HDC["id"], by="Ada Admin")
ok("2. 🔴 a reviewer needs a group", clp_reviews.add_reviewer("x@example.org", "X", "rg-nope")[1] == "Pick the client's group.")
ok("2. 🔴 users.create_user never makes a staff role 'reviewer'",
   users.create_user("y@example.org", "Y", "reviewer")[0] is None)
ok("2. 🔴 a reviewer stays a reviewer (role or team refused)",
   users.update_user(SAM["id"], {"role": "admin"})[1] == "A client reviewer stays a client reviewer."
   and status_of(lambda: main.admin_user_change(SAM["id"], main.UserPatch(role="admin"), None)) == 400)
ok("2. an end date in the past is refused", clp_reviews.ends_at("2020-01-01")[1] == "The end date must be after today.")
ok("2. an end date is the start of that day", clp_reviews.ends_at("2099-03-04") == ("2099-03-04T00:00:00Z", None))
ok("2. the People tab does not list reviewers; the Client reviewers tab does",
   all(u["kind"] != "reviewer" for u in main.admin_users(None)["users"])
   and {r["email"] for r in main.admin_reviewers(None)["reviewers"]} == {"sam.reviewer@example.org", "alex@example.org",
                                                                       "hal@example.org"})
ok("2. 🔴 access_for refuses a reviewer", isinstance(_raises(lambda: users.access_for(users.get_user(SAM["id"]))), ValueError))
ok("2. 🔴 two-step sign-in is required for a reviewer", users.needs_two_step(users.get_user(SAM["id"])))
SENT.clear()
_inv = main._invite_or_reset(users.get_user(SAM["id"]))
ok("2. the invite email says what the login is for",
   _inv["email"] == "sent" and SENT and SENT[0]["Subject"] == "Your Wayscope sign-in to review CLPs"
   and "National Highways" in SENT[0].get_content(), str(SENT[0]["Subject"] if SENT else None))


def sign_in_reviewer(user):
    """A real two-step set-up and a session, as the sign-in page does it."""
    users.set_password(user["id"], "a-long-reviewer-passphrase")
    u = users.get_user(user["id"])
    st = users.start_two_step(u)
    key = users.get_user(user["id"])["totp_pending"]
    got, codes, err, status = users.finish_setup(st["ticket"], users.totp_at(key, users.totp_step()))
    assert got, err
    raw, _ttl = users.create_session(user["id"])
    return raw


RAW_SAM = sign_in_reviewer(SAM)
RAW_ALEX = sign_in_reviewer(ALEX)
RAW_HAL = sign_in_reviewer(HAL)
ok("2. ⭐🔴 THE WALL: a reviewer's session never resolves to staff access", users.resolve_session(RAW_SAM) == (None, None))
_rev, _u = users.resolve_reviewer(RAW_SAM)
ok("2. ...only resolve_reviewer() reads it: their name and group", _rev and _rev["via"] == "reviewer"
   and _rev["group_id"] == NH["id"] and _rev["group_name"] == "National Highways" and "role" not in _rev)
_tok = access.set_current(None, RAW_SAM)
ok("2. ⭐🔴 access.set_current(cookie of a reviewer): current() is None, reviewer() is them",
   access.current() is None and (access.reviewer() or {}).get("user_id") == SAM["id"])
access.reset_current(_tok)
_tok = access.set_current(None, users.create_session(U_PAT["id"])[0]) if users.two_step_on(users.get_user(U_PAT["id"])) else None
if _tok:
    access.reset_current(_tok)
REV_SAM = users.resolve_reviewer(RAW_SAM)[0]
REV_ALEX = users.resolve_reviewer(RAW_ALEX)[0]
REV_HAL = users.resolve_reviewer(RAW_HAL)[0]

# =========================================================================== #
#  3. 🔴 every staff guard and helper refuses a reviewer                       #
# =========================================================================== #
as_rev(REV_SAM)
ok("3. ⭐🔴 _require_access refuses a reviewer (401), as it refuses nobody signed in",
   status_of(main._require_access) == 401)
ok("3. 🔴 the CLP list, a CLP, its notes, a draft and an issue: all refused",
   all(status_of(fn) == 401 for fn in (main.clp_documents_list, lambda: main.clp_documents_get(Y_ALL),
                                         lambda: main.clp_notes_read(Y_ALL), lambda: main.clp_documents_draft(Y_ALL),
                                         lambda: main.clp_documents_issue(Y_ALL, 1))))
ok("3. 🔴 an admin endpoint refuses a reviewer", status_of(lambda: main.admin_users(None)) == 403)
for _fake in (REV_SAM, dict(REV_SAM, role="admin"), {"via": "reviewer", "role": "planner", "ipt": None},
              {"via": "login", "role": "reviewer", "ipt": None}):
    ok(f"3. 🔴 access helpers refuse a reviewer-shaped dict {sorted(_fake)[:3]}",
       not access.line_visible({"ipt": None}, _fake) and not access.can_approve(_fake) and access.describe(_fake) is None
       and access.ipt_for_save("IPT1", _fake)[1] and not clp_records.visible({"team": None}, _fake))
access._ACCESS.set(dict(REV_SAM))
ok("3. 🔴 even if a reviewer's dict reached the staff context, current() hands back None", access.current() is None)
as_rev(REV_SAM)
ok("3. 🔴 the auth answer for a reviewer has no access", main.auth_me()["access"] is None
   and main.auth_me()["reviewer"]["group_name"] == "National Highways" and main.auth_me()["signed_in"])

# =========================================================================== #
#  4. Sending an issued CLP (planners and admins)                              #
# =========================================================================== #
as_(PAT)
_r = clp_reviews.send_issue(Y_ALL, None, [NH["id"]], PAT, factors)
ok("4. 🔴 a CLP with no issue is never sent (a draft never goes)", _r.get("status") == 422 and "Approve" in _r["error"], str(_r))
_ap = clp_records.approve(Y_ALL, "First issue for the client", PAT, factors, 22.0, build_fast)
ok("4. approve as Issue 1", _ap.get("last_issue", {}).get("no") == 1, str(_ap)[:200])
_pv = clp_records.preview(Y_ALL, PAT, factors, 22.0)
ok("4. the approve card lists the live groups to tick, none had an issue yet",
   [g["name"] for g in _pv["review_groups"]] == ["Harborough District Council", "National Highways"]
   and all(g["had_issue"] is None for g in _pv["review_groups"]) and _pv["review_groups"][1]["reviewers"] == 2)
as_(NORA)
ok("4. 🔴 a team cannot send", clp_reviews.send_issue(Y_ALL, 1, [NH["id"]], NORA, factors).get("status") in (403, 404))
as_(PAT)
SENT.clear()
_r = main.clp_documents_review_send(Y_ALL, main.ClpReviewSendIn(groups=[NH["id"]], issue_no=1))
ok("4. ⭐ a planner sends Issue 1 to National Highways", _r["sent"] and _r["sent"][0]["group_id"] == NH["id"]
   and _r["sent"][0]["email"] == {"sent": 2, "unsent": 0, "failed": 0}, str(_r))
ok("4. ⭐ one email to each reviewer in the group, no file attached",
   sorted(m["To"] for m in SENT) == ["alex@example.org", "sam.reviewer@example.org"]
   and all(not list(m.iter_attachments()) for m in SENT)
   and SENT[0]["Subject"] == "A CLP to review: Yard East, Issue 1" and "#review" in SENT[0].get_content()
   and "Pat Planner of Test contractor" in SENT[0].get_content() and "First issue for the client" in SENT[0].get_content()
   and "DEMO · Fictional scheme" in SENT[0].get_content(), str([m["Subject"] for m in SENT]))
ok("4. 🔴 the email names no team id", not any(re.search(r"IPT ?[1-6]", m.as_string()) for m in SENT))
SENT.clear()
_r = clp_reviews.send_issue(Y_ALL, 1, [NH["id"]], PAT, factors)
ok("4. sending the same issue again is skipped, no second email", _r["skipped"] and not _r["sent"] and not SENT)
_ap = clp_records.approve(P_ALL, None, PAT, factors, 22.0, build_fast)
ok("4. another CLP approved (Issue 1 of the stockpile, not sent)", _ap.get("last_issue", {}).get("no") == 1)
ok("4. 🔴 a stopped group cannot be sent to",
   clp_reviews.change_group(HDC["id"], stopped=True)[1] is None
   and clp_reviews.send_issue(P_ALL, 1, [HDC["id"]], PAT, factors).get("status") == 422)
ok("4. 🔴 stopping a group ends its reviewers' sessions and refuses them from then on",
   users.resolve_reviewer(RAW_HAL) == (None, None) and not users.usable(users.get_user(HAL["id"])))
clp_reviews.change_group(HDC["id"], stopped=False)
ok("4. ...started again, its reviewer signs in again (a new session)", users.usable(users.get_user(HAL["id"])))
RAW_HAL = users.create_session(HAL["id"])[0]
REV_HAL = users.resolve_reviewer(RAW_HAL)[0]
ok("4. 🔴 a group a CLP went to cannot be deleted", "Stop it instead" in (clp_reviews.delete_group(NH["id"]) or ""))
ok("4. the contractor's thread shows the send as a grey line",
   any(n["kind"] == "step" and n["step"] == "review-sent" and n["step_word"] == "Issue 1 sent to National Highways"
       and n["by"] == "Pat Planner" for n in clp_notes.thread(Y_ALL, PAT)["notes"]))
_so = main.clp_documents_review_options(Y_ALL)
ok("4. ⭐ ⋯ → Send Issue N to reviewers… reads the last issue and the live groups, National Highways marked as having it",
   _so["issue_no"] == 1 and [(g["name"], g["has_this"], g["had_issue"]) for g in _so["groups"]]
   == [("Harborough District Council", False, None), ("National Highways", True, 1)], str(_so))
ok("4. 🔴 ...a CLP with no issue answers 422 (nothing to send), one that does not exist 404",
   status_of(lambda: main.clp_documents_review_options(Y_N)) == 422 and status_of(lambda: main.clp_documents_review_options("clp-nope")) == 404)
as_(NORA)
ok("4. 🔴 ...a team cannot read the send options", status_of(lambda: main.clp_documents_review_options(Y_ALL)) == 403)
as_(PAT)

# =========================================================================== #
#  5. 🔴 THE WALL on the review reads                                          #
# =========================================================================== #
BUILDS = {"n": 0}
_real_build, _real_gather, _real_main_build = clp_doc.build, clp_doc.gather, main._clp_build


def _count(fn):
    def wrap(*a, **k):
        if access.reviewer() is not None:      # only what a REVIEWER's request makes (a planner's approve builds)
            BUILDS["n"] += 1
        return fn(*a, **k)
    return wrap


clp_doc.build, clp_doc.gather, main._clp_build = _count(_real_build), _count(_real_gather), _count(_real_main_build)
as_rev(REV_SAM)
_l = main.review_clps()
ok("5. ⭐ a reviewer lists only the CLP sent to their group",
   [c["id"] for c in _l["clps"]] == [Y_ALL] and _l["clps"][0]["state"] == "waiting" and _l["group_name"] == "National Highways"
   and _l["clps"][0]["team_name"] == "All teams" and _l["clps"][0]["issue_no"] == 1, str(_l)[:300])
_one = main.review_clp(Y_ALL)
ok("5. one CLP: its issue, the note sent, can decide", _one["latest"]["no"] == 1 and _one["can_decide"]
   and _one["latest"]["note"] == "First issue for the client")
_f = main.review_clp_issue(Y_ALL, 1, _Request())
_stored = db.query("SELECT file_b64 FROM clp_issues WHERE tenant_id = ? AND clp_id = ? AND issue_no = 1",
                   (db.current_tenant(), Y_ALL))[0]["file_b64"]
ok("5. ⭐ the download is the issue EXACTLY as approved (the stored file)", _f.body == base64.b64decode(_stored))
ok("5. 🔴 a CLP not sent to the group (approved, never sent) is a 404", status_of(lambda: main.review_clp(P_ALL)) == 404
   and status_of(lambda: main.review_clp_issue(P_ALL, 1, _Request())) == 404)
ok("5. 🔴 a draft (never issued) is a 404", status_of(lambda: main.review_clp(Y_N)) == 404)
ok("5. 🔴 a CLP that does not exist is the same 404", status_of(lambda: main.review_clp("clp-nope")) == 404)
ok("5. 🔴 an issue number never sent is a 404", status_of(lambda: main.review_clp_issue(Y_ALL, 2, _Request())) == 404)
as_rev(REV_HAL)
ok("5. ⭐🔴 another group cannot read National Highways' CLP, its file, comment or decide on it",
   main.review_clps()["clps"] == [] and status_of(lambda: main.review_clp(Y_ALL)) == 404
   and status_of(lambda: main.review_clp_issue(Y_ALL, 1, _Request())) == 404
   and status_of(lambda: main.review_clp_comment(Y_ALL, main.ReviewCommentIn(words="hi"))) == 404
   and status_of(lambda: main.review_clp_decision(Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="accepted"))) == 404)
as_(PAT)
ok("5. 🔴 a staff login has no review page (the review reads need a reviewer)", status_of(main.review_clps) == 401)
as_(None)
ok("5. 🔴 nor does a visitor", status_of(main.review_clps) == 401 and status_of(lambda: main.review_clp(Y_ALL)) == 401)
ok("5. 🔴 a forged reviewer dict with a stopped or missing group reads nothing",
   clp_reviews.list_for_reviewer(dict(REV_SAM, group_id="rg-nope")) is None
   and clp_reviews.clp_for_reviewer(Y_ALL, {"via": "login", "group_id": NH["id"]}) is None)

# =========================================================================== #
#  6. Comments and the group's decision                                        #
# =========================================================================== #
as_rev(REV_ALEX)
SENT.clear()
_c = main.review_clp_comment(Y_ALL, main.ReviewCommentIn(words="4.1 does not give the Saturday hours."))
ok("6. a reviewer comments; it shows in their thread with the group", any(
    n["kind"] == "note" and n["reviewer"] and n["org"] == "National Highways" and n["by"] == "Alex Example"
    for n in _c["thread"]))
ok("6. ⭐ a comment sends nothing (Q7)", SENT == [])
ok("6. 🔴 Return needs a comment", status_of(lambda: main.review_clp_decision(
    Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="returned"))) == 422)
ok("6. an unknown decision is refused", status_of(lambda: main.review_clp_decision(
    Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="approved"))) == 422)
_d = main.review_clp_decision(Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="returned",
                                                         words="Add the Saturday hours to 4.1."))
ok("6. ⭐ the first reviewer's decision stands for the group, with their name",
   _d["latest"]["state"] == "returned" and _d["latest"]["by"] == "Alex Example")
ok("6. ⭐ one email to the person who sent it", len(SENT) == 1 and SENT[0]["To"] == "pat@example.com"
   and SENT[0]["Subject"] == "Returned by National Highways: Yard East, Issue 1"
   and "Add the Saturday hours" in SENT[0].get_content() and "#clp" in SENT[0].get_content(), str([m["Subject"] for m in SENT]))
as_rev(REV_SAM)
_d = main.review_clp_decision(Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="accepted"))
ok("6. ⭐ another reviewer in the group changes it while the issue is the latest; every decision is kept",
   _d["latest"]["state"] == "accepted" and _d["latest"]["by"] == "Sam Reviewer"
   and [x["decision"] for x in _d["latest"]["decisions"]] == ["returned", "accepted"])
as_(PAT)
_lst = {c["id"]: c for c in clp_records.list_for(PAT)["clps"]}
ok("6. ⭐ the contractor's list says where it stands with the group",
   _lst[Y_ALL]["reviews"] == [dict(_lst[Y_ALL]["reviews"][0], group_name="National Highways", state="accepted",
                                   by="Sam Reviewer", issue_no=1)] and _lst[P_ALL]["reviews"] == [], str(_lst[Y_ALL]["reviews"]))
ok("6. the list says when there are groups (the Reviewers filter)", clp_records.list_for(PAT)["review_groups"] is True)
_th = clp_notes.thread(Y_ALL, PAT)
# NARROWED 31 Oct 2026 (PR 3d, Q3): the comment is in National Highways' own tab (`clients`), no longer the contractor's
_cl = {c["name"]: c for c in _th["clients"]}
_rn = [n for n in _cl["National Highways"]["notes"] if n["kind"] == "note" and n.get("reviewer")]
ok("6. ⭐ in the client's tab: the comment with the group, Make a task for a planner, never deleted",
   _rn and _rn[0]["org"] == "National Highways" and _rn[0]["can_task"] and not _rn[0]["can_delete"])
ok("6. 🔴 PR 3d (Q3): the contractor's own notes hold no client comment",
   not any(n["kind"] == "note" and "Saturday hours" in (n.get("words") or "") for n in _th["notes"]))
ok("6. the decisions as grey lines", [n["step_word"] for n in _th["notes"] if n["kind"] == "step"
                                      and n["step"].startswith("review-")] == ["Issue 1 sent to National Highways",
                                                                               "Issue 1 returned", "Issue 1 accepted"])
ok("6. 🔴 a planner cannot delete a reviewer's comment", clp_notes.remove(Y_ALL, _rn[0]["id"], PAT).get("status") == 403)
_t = clp_notes.add_task(Y_ALL, {"words": "Put the Saturday hours in 4.1", "for": "approvers", "from_note": _rn[0]["id"]},
                        PAT, factors)
# NARROWED 31 Oct 2026 (PR 3d, Q6): the task lands in the client's tab and says whose note it came from
ok("6. ⭐ Make a task from a reviewer's comment: in the client's tab, it says whose note it came from",
   "id" in _t and [t for t in {c["name"]: c for c in _t["thread"]["clients"]}["National Highways"]["tasks"]
                   if t["id"] == _t["id"]][0]["from_note_by"] == "Alex Example"
   and not any(t["id"] == _t["id"] for t in _t["thread"]["tasks"]))
as_(NORA)
ok("6. 🔴 a team cannot make a task from the client's comment (planners and admins)",
   clp_notes.add_task(Y_ALL, {"words": "x", "for": "approvers", "from_note": _rn[0]["id"]}, NORA, factors).get("status") in (403, 404))
as_(PAT)
_n1 = clp_notes.add_note(Y_ALL, "Gate B's Saturday shift is not agreed yet.", PAT, factors)
_n2 = clp_notes.add_note(Y_ALL, "Saturday 08:00-13:00 is now in 4.1.", PAT, factors, show_to=NH["id"])
ok("6. 🔴 a note shown to a group the CLP was not sent to is refused",
   clp_notes.add_note(Y_ALL, "x", PAT, factors, show_to=HDC["id"]).get("status") == 422)
# NARROWED 31 Oct 2026 (PR 3d, Q2): "Show to" now writes in the group's tab; the contractor's tab no longer has it
ok("6. a contractor note shown to the group is in the group's tab",
   any(n.get("words") == "Saturday 08:00-13:00 is now in 4.1." for n in {c["name"]: c for c in _n2["thread"]["clients"]}["National Highways"]["notes"])
   and not any(n.get("words") == "Saturday 08:00-13:00 is now in 4.1." for n in _n2["thread"]["notes"]))
as_rev(REV_SAM)
_rt = main.review_clp(Y_ALL)["thread"]
# NARROWED 31 Oct 2026 (PR 3d, Q5): the reviewer now reads the group's TASKS too (a separate list); never the
# contractor's own notes or tasks
ok("6. ⭐🔴 a reviewer reads their group's comments, the lines and the note shown to them — never a task or another note",
   any(n.get("words") == "Saturday 08:00-13:00 is now in 4.1." and n.get("org") == "Test contractor" for n in _rt)
   and not any("not agreed" in (n.get("words") or "") for n in _rt)
   and not any("Put the Saturday hours" in (n.get("words") or "") for n in _rt)
   and all(n["kind"] in ("note", "step") for n in _rt), json.dumps(_rt)[:400])
as_rev(REV_HAL)
ok("6. 🔴 another group's reviewer gets none of it", status_of(lambda: main.review_clp(Y_ALL)) == 404
   and clp_notes.review_thread(Y_ALL, HDC["id"]) == [])

# =========================================================================== #
#  7. A newer issue starts fresh; the history                                  #
# =========================================================================== #
as_(PAT)
SENT.clear()
_ap = main.clp_documents_approve(Y_ALL, main.ClpNoteIn(note="Saturday hours added to 4.1", send_to=[NH["id"]]))
ok("7. ⭐ approve with the ticks: Issue 2 kept and sent to the group in one step",
   _ap["last_issue"]["no"] == 2 and _ap["review_send"]["sent"][0]["group_id"] == NH["id"] and len(SENT) == 2, str(_ap.get("review_send")))
ok("7. the approve card ticks a group that had the last issue",
   [g for g in clp_records.preview(Y_ALL, PAT, factors, 22.0)["review_groups"] if g["id"] == NH["id"]][0]["had_issue"] == 2)
as_rev(REV_ALEX)
_one = main.review_clp(Y_ALL)
ok("7. ⭐ a newer issue starts a fresh decision", _one["latest"]["no"] == 2 and _one["latest"]["state"] == "waiting"
   and [i["no"] for i in _one["issues"]] == [2, 1] and _one["issues"][1]["state"] == "accepted")
ok("7. 🔴 an older issue can no longer be decided", status_of(lambda: main.review_clp_decision(
    Y_ALL, main.ReviewDecisionIn(issue_no=1, decision="returned", words="late"))) == 422)
ok("7. both issues download", main.review_clp_issue(Y_ALL, 2, _Request()).body and main.review_clp_issue(Y_ALL, 1, _Request()).body)
_hist = clp_records.doc_history(Y_ALL)
# NARROWED 31 Oct 2026 (security review, finding 1): the group only, no reviewer's own name in the issued file
ok("7. ⭐ the Document history prints the group's decision on Issue 1 (Q10)",
   any(h["no"] == 1 and h["words"] == "Accepted by National Highways." for h in _hist)
   and not any("Returned by" in (h.get("words") or "") for h in _hist), str(_hist))
ok("7. ...and the Word file of Issue 2 carries it", "Accepted by National Highways." in "\n".join(
    p.text for t in __import__("docx").Document(io.BytesIO(main.review_clp_issue(Y_ALL, 2, _Request()).body)).tables
    for row in t.rows for p in row.cells[-1].paragraphs))
ok("7. ⭐🔴 a reviewer's whole visit built NOTHING (no Word file, no gather)", BUILDS["n"] == 0, str(BUILDS))
clp_doc.build, clp_doc.gather, main._clp_build = _real_build, _real_gather, _real_main_build
as_(PAT)
_m1 = clp_reviews.marker(Y_ALL)
as_rev(REV_ALEX)
main.review_clp_decision(Y_ALL, main.ReviewDecisionIn(issue_no=2, decision="accepted"))
ok("7. a kept draft's key moves with a decision (clp_reviews.marker)", clp_reviews.marker(Y_ALL) != _m1)

# =========================================================================== #
#  8. The audit trail                                                          #
# =========================================================================== #
_aud = db.query("SELECT kind, actor_kind, actor_label, path FROM audit_log WHERE tenant_id = ? ORDER BY at, id",
                (db.current_tenant(),))
ok("8. ⭐ a download is in the audit trail with the reviewer's name and group",
   any(a["kind"] == "review-download" and a["actor_kind"] == "reviewer"
       and a["actor_label"] == "Alex Example <alex@example.org> · National Highways" for a in _aud))
ok("8. ⭐ a reviewer's sign-in events name the group", any(a["kind"] == "two-step-on" and a["actor_kind"] == "reviewer"
                                                         and "· National Highways" in a["actor_label"] for a in _aud))
as_rev(REV_SAM)
_req = _Request(headers={"content-type": "application/json"})
main._audit_write(_req, f"/api/review/clps/{Y_ALL}/comments", "POST", 200, b'{"words":"x"}')
_last = db.query("SELECT kind, actor_kind, actor_label FROM audit_log WHERE tenant_id = ? ORDER BY at DESC, id DESC",
                 (db.current_tenant(),))[0]
ok("8. ⭐ a reviewer's write is audited under their name and group (the middleware's writer)",
   _last["actor_kind"] == "reviewer" and _last["actor_label"].endswith("· National Highways"), str(_last))
ok("8. the reviewer writes keep the kept reads (no data version bump), like the CLP notes",
   main._REVIEW_PATH.match(f"/api/review/clps/{Y_ALL}/decision") and main._REVIEW_PATH.match("/api/admin/reviewers")
   and main._REVIEW_PATH.match("/api/admin/reviewer-groups/rg-1") and main._REVIEW_PATH.match(f"/api/clp/documents/{Y_ALL}/review-send")
   and not main._REVIEW_PATH.match(f"/api/clp/documents/{Y_ALL}/approve") and not main._REVIEW_PATH.match("/api/admin/users"))

# =========================================================================== #
#  9. Logins: end date, disable, delete, group change                           #
# =========================================================================== #
as_(ADA)
_u, err = clp_reviews.change_reviewer(ALEX["id"], {"disabled": True})
ok("9. disabling a reviewer signs them out", not err and users.resolve_reviewer(RAW_ALEX) == (None, None))
_u, err = clp_reviews.change_reviewer(ALEX["id"], {"disabled": False, "ends_on": "2099-01-01"})
ok("9. an end date is kept", _u["expires_at"] == "2099-01-01T00:00:00Z" and not err)
db.execute("UPDATE users SET expires_at = ? WHERE tenant_id = ? AND id = ?", ("2020-01-01T00:00:00Z", db.current_tenant(), ALEX["id"]))
ok("9. 🔴 past their end date a reviewer cannot sign in", not users.usable(users.get_user(ALEX["id"]))
   and users.resolve_reviewer(users.create_session(ALEX["id"])[0]) == (None, None))
_u, err = clp_reviews.change_reviewer(HAL["id"], {"group_id": NH["id"]})
ok("9. moving a reviewer to another group signs them out", not err and _u["review_group"] == NH["id"]
   and users.resolve_reviewer(RAW_HAL) == (None, None))
ok("9. a staff login is not changed through the reviewer endpoints", clp_reviews.change_reviewer(U_PAT["id"], {"name": "x"})[1] == "No such login."
   and clp_reviews.delete_reviewer(U_PAT["id"]) == "No such login.")
# NARROWED 31 Oct 2026 (PR 3d): the comments are in the group's tab; the decisions stay grey lines in both
ok("9. deleting a reviewer keeps their comments and decisions", clp_reviews.delete_reviewer(ALEX["id"]) is None
   and users.get_user(ALEX["id"]) is None
   and any(n.get("by") == "Alex Example" for c in clp_notes.thread(Y_ALL, PAT)["clients"] for n in c["notes"]))
ok("9. a reviewer's sign-out opens nothing else (no map cookie), by source",
   'if rev:\n            # PR 3c: a reviewer signs out with nothing else opened (never the public map\'s cookie)' in
   open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read())

# =========================================================================== #
# 10. The organisation file, the demo, the landing form                        #
# =========================================================================== #
ok("10. ⭐ the organisation file carries the groups and the sends / decisions, after the CLPs",
   tenant_package.ORDER.index("clp_notes") < tenant_package.ORDER.index("clp_review_groups") < tenant_package.ORDER.index("clp_reviews"))
ok("10. 🔴 never the reviewer logins (users is not package data)", "users" not in tenant_package.ORDER and "users" not in db.TENANTED_TABLES)
ok("10. both tables are tenanted and build no figure", {"clp_review_groups", "clp_reviews"} <= set(db.TENANTED_TABLES)
   and {"clp_review_groups", "clp_reviews"} <= db.NO_DATA_TABLES)
_pkg = json.load(open(os.path.join(ROOT, "demo", "uk-corridor.package.json"), encoding="utf-8"))
ok("10. ⭐ the demo ships ONE fictional group and no reviewer logins (Q11)",
   [(g["id"], g["name"]) for g in _pkg["tables"].get("clp_review_groups", [])] == [("rg-demo", "Highways client (fictional)")]
   and _pkg["tables"].get("clp_reviews", []) == [] and "users" not in _pkg["tables"])
_mdt = open(os.path.join(BACKEND, "tools", "make_demo_tenant.py"), encoding="utf-8").read()
ok("10. a demo refresh keeps live's sends and decisions, and merges the groups by id",
   '"clp_notes", "clp_reviews",' in _mdt and 'nt["clp_review_groups"] = list(lt.get("clp_review_groups") or []) + [' in _mdt)
_dr = open(os.path.join(BACKEND, "users.py"), encoding="utf-8").read()
ok("10. 🔴 the landing demo form only ever makes a DEMO login, never a reviewer",
   re.findall(r'create_user\(email, name or email, "team", demo_slot\(\), kind="(\w+)"', _dr) == ["demo"])

# =========================================================================== #
# 11. The wall, by source                                                      #
# =========================================================================== #
MAIN = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
REV = open(os.path.join(BACKEND, "clp_reviews.py"), encoding="utf-8").read().split('"""', 2)[2]   # the code, not the docstring
REV = "\n".join(l for l in REV.splitlines() if not l.strip().startswith("#"))
_review_eps = re.findall(r'@app\.(?:get|post|patch|delete)\("/api/review/[^"]*"\)\ndef (\w+)\(([^)]*)\):\n((?:    .*\n|\n)+?)(?=\n\S|\Z)', MAIN)
# NARROWED 31 Oct 2026 (PR 3d): + the reviewer's task add / change / delete and their own note's delete
ok("11. nine review endpoints", len(_review_eps) == 9, str([e[0] for e in _review_eps]))
ok("11. 🔴 every review endpoint takes the reviewer and never the staff access",
   all("_require_reviewer()" in body and "_require_access" not in body and "access.current" not in body
       for _n, _a, body in _review_eps))
ok("11. 🔴 clp_reviews never reads the staff access for the reviewer side, and builds nothing",
   "access.current" not in REV and "clp_doc.build" not in REV and "clp_doc.gather" not in REV and "_clp_build" not in REV)
ok("11. 🔴 resolve_session refuses a reviewer before anything else is read",
   "if not usable(user, now) or is_reviewer(user):\n        return None, None" in open(os.path.join(BACKEND, "users.py"), encoding="utf-8").read())
ok("11. 🔴 a reviewer cookie write needs the app's header (the middleware)", "or access.reviewer() is not None" in MAIN)
ok("11. 🔴 the gate never opens for a reviewer: it asks access.current() only",
   "has_valid_code=bool(access.current())," in MAIN)

# =========================================================================== #
# 12. The security review's findings (31 Oct 2026), each fixed                  #
# =========================================================================== #
as_(NORA)
clp_records.send(Y_N, "Team only: Bob still owes the gate B hours", NORA, factors)
as_(PAT)
_apn = clp_records.approve(Y_N, None, PAT, factors, 22.0, build_fast)
SENT.clear()
_sn = clp_reviews.send_issue(Y_N, _apn["last_issue"]["no"], [NH["id"]], PAT, factors)
ok("12. 🔴 (finding 2) the team's note to the approver never reaches the client — not in the email",
   _sn["sent"] and SENT and not any("Bob still owes" in m.get_content() for m in SENT), str([m.get_content()[:200] for m in SENT]))
as_rev(REV_SAM)
ok("12. 🔴 (finding 2) ...nor on the review page (an issue approved with no note shows none)",
   main.review_clp(Y_N)["latest"]["note"] is None and "Bob still owes" not in json.dumps(main.review_clp(Y_N)))
as_(NORA)
# NARROWED 31 Oct 2026 (PR 3d, Q4): the team has no client tabs at all
ok("12. 🔴 (finding 3) a team login cannot show a note to the client's reviewers (403), nor is it offered the groups",
   clp_notes.add_note(Y_N, "Team words for the client", NORA, factors, show_to=NH["id"]).get("status") == 403
   and clp_notes.thread(Y_N, NORA)["clients"] == []
   and not any("Team words for the client" in (n.get("words") or "") for n in clp_notes.thread(Y_N, NORA)["notes"]))
ok("12. ...a team's plain note still works", "id" in clp_notes.add_note(Y_N, "A plain team note", NORA, factors))
as_(PAT)
# NARROWED 31 Oct 2026 (PR 3d): the group the CLP went to is a tab
ok("12. ...a planner is offered the group the CLP went to", [g["name"] for g in clp_notes.thread(Y_N, PAT)["clients"]] == ["National Highways"])
_hist2 = clp_records.doc_history(Y_ALL)
ok("12. 🔴 (finding 1) the issued file names no reviewer, only their group while the CLP went to that one group alone",
   any(h["no"] == 1 and h["words"] == "Accepted by National Highways." for h in _hist2)
   and not any("Sam Reviewer" in (h.get("words") or "") or "(" in (h.get("words") or "") for h in _hist2 if h.get("no") == 1 and not h.get("by")), str(_hist2))
clp_reviews.send_issue(Y_ALL, 2, [HDC["id"]], PAT, factors)
_hist3 = clp_records.doc_history(Y_ALL)
ok("12. 🔴 (finding 1) once the CLP went to a second group, a decision line names no group: 'by the client's reviewers'",
   any(h["no"] == 1 and h["words"] == "Accepted by the client's reviewers." for h in _hist3)
   and not any("National Highways" in (h.get("words") or "") for h in _hist3 if not h.get("by")), str(_hist3))
ok("12. 🔴 (finding 4) a group name with a line break is refused; a reviewer's name too",
   clp_reviews.add_group("Evil\r\nBcc: x@evil.test", "Ada Admin")[1] == "Write the name on one line."
   and clp_reviews.change_group(NH["id"], name="NH\nBcc: x@evil.test")[1] == "Write the name on one line."
   and clp_reviews.add_reviewer("ev@example.org", "Eve\r\nBcc: x@evil.test", NH["id"], by="Ada Admin")[1] == "Write the name on one line.")
_cn = clp_records.create({"name": "Yard\r\nBcc: x@evil.test", "location_ids": [YARD]}, PAT, factors)
ok("12. 🔴 (finding 4) a CLP's name is kept on one line", _cn.get("name") == "Yard Bcc: x@evil.test", str(_cn)[:200])
_ok_rev = users.get_user(SAM["id"])
ok("12. 🔴 (finding 4) an email header never takes a line break, and a message that cannot be built is a failed email, never a raise",
   "\n" not in clp_reviews.send_message(_ok_rev, {"name": "A\r\nB", "team": None}, {"issue_no": 1}, "Pat",
                                        {"DEMO_FROM": "a@example.org", "reply_to": "a@example.org"}, "G")["Subject"])
_real_sm = clp_reviews.send_message
clp_reviews.send_message = lambda *a, **k: (_ for _ in ()).throw(ValueError("bad header"))
_real_ms = users.mail_settings
users.mail_settings = lambda: {"DEMO_FROM": "a@example.org", "reply_to": "a@example.org"}
try:
    _t = clp_reviews.email_reviewers(NH["id"], {"name": "Yard East", "team": None}, {"issue_no": 1}, "Pat")
finally:
    clp_reviews.send_message, users.mail_settings = _real_sm, _real_ms
ok("12. ...email_reviewers counts it failed", _t["failed"] >= 1 and _t["sent"] == 0, str(_t))
_before = users.get_user(HAL["id"])["name"]
_u, err = clp_reviews.change_reviewer(HAL["id"], {"name": "Hal Renamed", "group_id": "rg-nope"})
ok("12. 🔴 (finding 6) a refused group move saves nothing else", err == "Pick a group that is not stopped."
   and users.get_user(HAL["id"])["name"] == _before)
_raw = users.create_session(SAM["id"])[0]
users._make_admin(SAM["id"])
ok("12. 🔴 (finding 5) a promotion to admin ends every session the login had (a reviewer's cookie never becomes an admin's)",
   users.resolve_session(_raw) == (None, None) and users.resolve_reviewer(_raw) == (None, None))

print(f"test_clp_reviewers: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
