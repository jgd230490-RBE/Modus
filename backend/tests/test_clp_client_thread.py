"""
The client's OWN notes and tasks on a CLP, 31 Oct 2026 (task 4a, PR 3d) — backend/clp_notes.py ("TWO THREADS"),
clp_reviews.task / change_task / remove and the /api/review/clps/{id}/tasks, /notes endpoints. Mockup
notes/clp-client-thread-mockup-1031/ (John: "the client and admin/planner should also have notes and task seperatly
between each other"; Q1–Q10 as recommended).

What is asserted: each group a CLP was sent to has its own thread (planners / admins + that group's reviewers); the
contractor's thread keeps only the send / decision lines of it; 🔴 a team login never reads, counts, finds or writes a
client thread (Q4); tasks both ways, each side ticks its own and changes only what its side wrote (Q5, Q10); Make a
task from a client note lands in the client thread (Q6); the counts (Q8); the one email to a named person, a reviewer's
link opening CLPs for review (Q9); 🔴 another group's reviewer reaches none of it; a stopped group's thread is read-only;
nothing of either thread is in the issued Word file.

WHAT THIS DOES NOT PROVE: the HTTP layer is stubbed (smoke_reviewer_wall.py drives the real app); SQLite only; the
emails are captured, never sent.

Run (PowerShell):  $env:PYTHONUTF8 = "1"; .venv-tests\\Scripts\\python backend/tests/test_clp_client_thread.py
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

TMP = tempfile.mkdtemp(prefix="rbe_clpct_")
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
#  0. Two groups, three reviewers; Yard East's team CLP and its every-team CLP #
#     approved and sent                                                        #
# =========================================================================== #
as_(ADA)
NH, _ = clp_reviews.add_group("National Highways", "Ada Admin")
HDC, _ = clp_reviews.add_group("Harborough District Council", "Ada Admin")
SAM, _ = clp_reviews.add_reviewer("sam.reviewer@example.org", "Sam Reviewer", NH["id"], by="Ada Admin")
ALEX, _ = clp_reviews.add_reviewer("alex@example.org", "Alex Example", NH["id"], by="Ada Admin")
HAL, _ = clp_reviews.add_reviewer("hal@example.org", "Hal Harborough", HDC["id"], by="Ada Admin")


def sign_in_reviewer(user):
    users.set_password(user["id"], "a-long-reviewer-passphrase")
    u = users.get_user(user["id"])
    st = users.start_two_step(u)
    key = users.get_user(user["id"])["totp_pending"]
    got, codes, err, status = users.finish_setup(st["ticket"], users.totp_at(key, users.totp_step()))
    assert got, err
    return users.resolve_reviewer(users.create_session(user["id"])[0])[0]


REV_SAM, REV_ALEX, REV_HAL = sign_in_reviewer(SAM), sign_in_reviewer(ALEX), sign_in_reviewer(HAL)
as_(NORA)
clp_records.send(Y_N, "Team only: the gate B hours are still with Bob", NORA, factors)
clp_notes.add_note(Y_N, "Our own note: Bob owes the gate hours", NORA, factors)
as_(PAT)
_ap = clp_records.approve(Y_N, "Issue 1 for the client", PAT, factors, 22.0, build_fast)
ok("0. the team's CLP approved as Issue 1", _ap.get("last_issue", {}).get("no") == 1, str(_ap)[:200])
clp_reviews.send_issue(Y_N, 1, [NH["id"]], PAT, factors)
_ap2 = clp_records.approve(Y_ALL, None, PAT, factors, 22.0, build_fast)
clp_reviews.send_issue(Y_ALL, 1, [NH["id"], HDC["id"]], PAT, factors)
SENT.clear()


def tab(clp, acc, name):
    return {c["name"]: c for c in clp_notes.thread(clp, acc, factors)["clients"]}.get(name)


def T(**k):
    return main.ReviewTaskIn(**k)


def CT(**k):
    return main.ClpTaskIn(**k)


# =========================================================================== #
#  1. Who sees which thread (Q1, Q3, Q4)                                       #
# =========================================================================== #
_th = clp_notes.thread(Y_N, PAT, factors)
ok("1. ⭐ a planner has one tab a group the CLP was sent to", [c["name"] for c in _th["clients"]] == ["National Highways"]
   and _th["clients"][0]["can_write"] and _th["clients"][0]["tasks"] == [])
ok("1. ⭐ the every-team CLP sent to two groups has two tabs, first sent first",
   [c["name"] for c in clp_notes.thread(Y_ALL, PAT, factors)["clients"]] == ["National Highways", "Harborough District Council"])
ok("1. 🔴 (Q4) the team has no client tab", clp_notes.thread(Y_N, NORA, factors)["clients"] == [])
ok("1. (Q3) the contractor's tab keeps the send as a grey line that opens the tab (a planner's)",
   any(n["kind"] == "step" and n["step"] == "review-sent" and n["group_id"] == NH["id"] for n in _th["notes"]))
ok("1. ...the team reads the same line, with no tab to open",
   any(n["kind"] == "step" and n["step"] == "review-sent" and n["group_id"] is None
       for n in clp_notes.thread(Y_N, NORA, factors)["notes"]))
ok("1. (Q4) the contractor's own note stays in the contractor's tab", any(
    "Bob owes" in (n.get("words") or "") for n in _th["notes"]))

# =========================================================================== #
#  2. Notes in the client's tab                                                #
# =========================================================================== #
as_(PAT)
_r = main.clp_notes_add(Y_N, main.ClpNoteIn(note="We will add the Saturday hours in Issue 2.", group=NH["id"]))
_nh = {c["name"]: c for c in _r["thread"]["clients"]}["National Highways"]
N_PAT = [n for n in _nh["notes"] if n["kind"] == "note"][-1]
ok("2. ⭐ a planner writes in the client's tab", N_PAT["words"] == "We will add the Saturday hours in Issue 2."
   and N_PAT["by"] == "Pat Planner" and N_PAT["can_delete"] and not N_PAT["reviewer"])
ok("2. 🔴 ...it is not in the contractor's tab", not any("Saturday hours in Issue 2" in (n.get("words") or "") for n in _r["thread"]["notes"]))
ok("2. 🔴 a group the CLP was not sent to is refused",
   status_of(lambda: main.clp_notes_add(Y_N, main.ClpNoteIn(note="x", group=HDC["id"]))) == 422)
as_(NORA)
ok("2. 🔴 (Q4) a team cannot write in the client's tab (403)",
   status_of(lambda: main.clp_notes_add(Y_N, main.ClpNoteIn(note="Team words to the client", group=NH["id"]))) == 403)
as_rev(REV_SAM)
_c = main.review_clp(Y_N)
ok("2. ⭐ the reviewer reads the planner's note, from the contractor", any(
    n.get("words") == "We will add the Saturday hours in Issue 2." and n["org"] == "Test contractor" for n in _c["thread"]))
ok("2. 🔴 ...and nothing of the contractor's tab (the team's notes, its note to the approver)",
   "Bob owes" not in json.dumps(_c) and "still with Bob" not in json.dumps(_c), json.dumps(_c)[:300])
_c = main.review_clp_comment(Y_N, main.ReviewCommentIn(words="Please show the Saturday hours for Gate B in section 5."))
N_SAM = [n for n in _c["thread"] if n["kind"] == "note" and n["reviewer"]][-1]
ok("2. a reviewer's note sends nothing", SENT == [])
as_(PAT)
_nh = tab(Y_N, PAT, "National Highways")
_sam = [n for n in _nh["notes"] if n.get("id") == N_SAM["id"]]
ok("2. ⭐ the planner reads it in the client's tab, Make a task offered, never deleted",
   _sam and _sam[0]["reviewer"] and _sam[0]["org"] == "National Highways" and _sam[0]["can_task"] and not _sam[0]["can_delete"])
ok("2. 🔴 (Q10) the contractor cannot delete the reviewer's note", status_of(lambda: main.clp_notes_delete(Y_N, N_SAM["id"])) == 403)
ok("2. 🔴 (Q3) ...and not in the contractor's tab",
   not any(n.get("id") == N_SAM["id"] for n in clp_notes.thread(Y_N, PAT, factors)["notes"]))
as_(NORA)
ok("2. 🔴 (Q4) the team finds neither note (a 404, as one that does not exist)",
   status_of(lambda: main.clp_notes_delete(Y_N, N_SAM["id"])) == 404 and status_of(lambda: main.clp_notes_delete(Y_N, N_PAT["id"])) == 404)

# =========================================================================== #
#  3. Tasks both ways; each side ticks its own (Q5)                            #
# =========================================================================== #
as_(PAT)
SENT.clear()
_r = main.clp_tasks_add(Y_N, CT(words="Confirm who signs off the traffic plan", group=NH["id"], **{"for": "group"}))
T_GROUP = _r["id"]
_t = {t["id"]: t for t in {c["name"]: c for c in _r["thread"]["clients"]}["National Highways"]["tasks"]}[T_GROUP]
ok("3. ⭐ a planner gives a task to the whole group", _t["for_word"] == "National Highways" and _t["for_side"] == "client"
   and not _t["can_tick"] and _t["can_change"] and not _t["mine"])
ok("3. (Q9) a task for a whole group sends nothing", SENT == [] and _r["email"] is None)
ok("3. 🔴 ...it is not a contractor task", not any(t["id"] == T_GROUP for t in _r["thread"]["tasks"]))
ok("3. 🔴 the contractor cannot tick the client's task",
   status_of(lambda: main.clp_tasks_change(Y_N, T_GROUP, CT(done=True))) == 403)
ok("3. 🔴 a team cannot be given a task in the client's tab",
   status_of(lambda: main.clp_tasks_add(Y_N, CT(words="x", group=NH["id"], **{"for": "team"}))) == 422)
as_rev(REV_ALEX)
_c = main.review_clp(Y_N)
_t = {t["id"]: t for t in _c["tasks"]}[T_GROUP]
ok("3. ⭐ the reviewer reads it as their group's, ticks it, cannot change its words",
   _t["for_word"] == "Your group" and _t["mine"] and _t["can_tick"] and not _t["can_change"])
ok("3. the reviewer's For list: the contractor, the group, the OTHER reviewer",
   [o["word"] for o in _c["for_options"]] == ["The contractor (planners and admins)", "Your group", "Sam Reviewer"])
_c = main.review_clp_task_change(Y_N, T_GROUP, T(done=True))
_t = {t["id"]: t for t in _c["tasks"]}[T_GROUP]
ok("3. ⭐ any reviewer in the group ticks a task for the group, with their name", _t["done"] and _t["done_by"] == "Alex Example")
ok("3. 🔴 a reviewer cannot change what the contractor wrote",
   status_of(lambda: main.review_clp_task_change(Y_N, T_GROUP, T(words="changed"))) == 403)
ok("3. 🔴 ...nor delete it", status_of(lambda: main.review_clp_task_delete(Y_N, T_GROUP)) == 403)
SENT.clear()
_c = main.review_clp_task(Y_N, T(words="Show the Saturday delivery hours in section 5", due="2026-11-07", **{"for": "approvers"}))
T_FOR_US = [t for t in _c["tasks"] if t["words"] == "Show the Saturday delivery hours in section 5"][0]
ok("3. ⭐ a reviewer gives the contractor a task", T_FOR_US["for_word"] == "The contractor" and T_FOR_US["for_side"] == "contractor"
   and T_FOR_US["can_change"] and not T_FOR_US["can_tick"] and T_FOR_US["by_client"] and T_FOR_US["due"] == "2026-11-07")
ok("3. (Q9) a task for the planners and admins sends nothing", SENT == [])
ok("3. ⭐ the reviewer's counts: open for the group / for the contractor", _c["task_counts"] == {"ours": 0, "theirs": 1})
ok("3. 🔴 a reviewer cannot tick the contractor's task",
   status_of(lambda: main.review_clp_task_change(Y_N, T_FOR_US["id"], T(done=True))) == 403)
ok("3. 🔴 a reviewer cannot give a task to a planner by name",
   status_of(lambda: main.review_clp_task(Y_N, T(words="x", **{"for": f"user:{U_PAT['id']}"}))) == 422)
ok("3. 🔴 nor to a reviewer of another group",
   status_of(lambda: main.review_clp_task(Y_N, T(words="x", **{"for": f"reviewer:{HAL['id']}"}))) == 422)
ok("3. 🔴 a reviewer's task body cannot pick another group's thread (only words, For and due are read)",
   "id" in str(main.review_clp_task(Y_N, T(words="Stays in ours", group=HDC["id"], **{"for": "group"})))
   and all(t["words"] != "Stays in ours" for c in clp_notes.thread(Y_ALL, PAT, factors)["clients"] for t in c["tasks"]))
as_(PAT)
_nh = tab(Y_N, PAT, "National Highways")
_t = {t["id"]: t for t in _nh["tasks"]}[T_FOR_US["id"]]
ok("3. ⭐ the planner reads the client's task: theirs to tick, not to change",
   _t["for_word"] == "Planners and admins" and _t["mine"] and _t["can_tick"] and not _t["can_change"] and _t["by_client"]
   and _t["written_by"] == "Alex Example")
ok("3. 🔴 the contractor cannot change or delete what the client wrote",
   status_of(lambda: main.clp_tasks_change(Y_N, T_FOR_US["id"], CT(words="x"))) == 403
   and status_of(lambda: main.clp_tasks_delete(Y_N, T_FOR_US["id"])) == 403)
_r = main.clp_tasks_change(Y_N, T_FOR_US["id"], CT(done=True))
ok("3. ⭐ the planner ticks it", {t["id"]: t for t in tab(Y_N, PAT, "National Highways")["tasks"]}[T_FOR_US["id"]]["done_by"] == "Pat Planner")
as_(NORA)
ok("3. 🔴 (Q4) the team finds no client task (404 on tick, change, delete)",
   all(status_of(fn) == 404 for fn in (lambda: main.clp_tasks_change(Y_N, T_GROUP, CT(done=False)),
                                         lambda: main.clp_tasks_change(Y_N, T_FOR_US["id"], CT(words="x")),
                                         lambda: main.clp_tasks_delete(Y_N, T_GROUP))))

# =========================================================================== #
#  4. Make a task from a client note (Q6)                                      #
# =========================================================================== #
as_(PAT)
_r = main.clp_tasks_add(Y_N, CT(words="Add the Gate B Saturday hours to 5", from_note=N_SAM["id"], **{"for": "approvers"}))
_t = {t["id"]: t for t in {c["name"]: c for c in _r["thread"]["clients"]}["National Highways"]["tasks"]}.get(_r["id"])
ok("4. ⭐ the task lands in the client's tab, says whose note it came from", _t and _t["from_note_by"] == "Sam Reviewer"
   and _t["for_word"] == "Planners and admins" and not any(t["id"] == _r["id"] for t in _r["thread"]["tasks"]))
ok("4. 🔴 a note from another tab cannot be named with this one",
   status_of(lambda: main.clp_tasks_add(Y_N, CT(words="x", from_note=N_SAM["id"], group=HDC["id"], **{"for": "approvers"}))) == 422)
as_(NORA)
ok("4. 🔴 a team cannot make a task from the client's note", status_of(
    lambda: main.clp_tasks_add(Y_N, CT(words="x", from_note=N_SAM["id"], **{"for": "team"}))) in (403, 404))

# =========================================================================== #
#  5. The one email (Q9)                                                       #
# =========================================================================== #
as_(PAT)
SENT.clear()
_r = main.clp_tasks_add(Y_N, CT(words="Check the Saturday hours", group=NH["id"], **{"for": f"reviewer:{SAM['id']}"}))
ok("5. ⭐ a task for one reviewer by name: one email, its link opens CLPs for review",
   _r["email"] == "sent" and len(SENT) == 1 and SENT[0]["To"] == "sam.reviewer@example.org"
   and "#review" in SENT[0].get_content() and "#clp" not in SENT[0].get_content()
   and SENT[0]["Subject"] == "A task on the CLP for Yard East", str([m.get_content()[:200] for m in SENT]))
ok("5. 🔴 the email names no team id", not any(re.search(r"IPT ?[1-6]", m.as_string()) for m in SENT))
SENT.clear()
_r = main.clp_tasks_add(Y_N, CT(words="Read section 5 again", group=NH["id"], **{"for": f"user:{U_ADA['id']}"}))
ok("5. ⭐ a task in the client's tab for one admin by name: one email, to the app's CLP page",
   _r["email"] == "sent" and len(SENT) == 1 and SENT[0]["To"] == "ada@example.com" and "#clp" in SENT[0].get_content())
SENT.clear()
ok("5. no email to yourself", main.clp_tasks_add(Y_N, CT(words="Mine", group=NH["id"], **{"for": f"user:{U_PAT['id']}"}))["email"] is None
   and SENT == [])
ok("5. 🔴 a planner by name must be a planner or an admin (never a team login)",
   status_of(lambda: main.clp_tasks_add(Y_N, CT(words="x", group=NH["id"], **{"for": f"user:{U_NORA['id']}"}))) == 422)
as_rev(REV_SAM)
SENT.clear()
_c = main.review_clp_task(Y_N, T(words="Send us the agreed hours", **{"for": f"reviewer:{ALEX['id']}"}))
ok("5. ⭐ a reviewer's task for the other reviewer: one email, to CLPs for review",
   len(SENT) == 1 and SENT[0]["To"] == "alex@example.org" and "#review" in SENT[0].get_content())
as_rev(REV_ALEX)
_t = [t for t in main.review_clp(Y_N)["tasks"] if t["words"] == "Send us the agreed hours"][0]
ok("5. ...Alex reads it as his, ticks it; Sam's name on it", _t["mine"] and _t["can_tick"] and not _t["can_change"]
   and _t["written_by"] == "Sam Reviewer" and _t["for_word"] == "Alex Example")
as_rev(REV_SAM)
ok("5. 🔴 ...Sam cannot tick a task given to Alex", status_of(lambda: main.review_clp_task_change(Y_N, _t["id"], T(done=True))) == 403)
ok("5. ...but changes what he wrote", "tasks" in main.review_clp_task_change(Y_N, _t["id"], T(due="2026-11-20")))

# =========================================================================== #
#  6. Deleting (Q10)                                                           #
# =========================================================================== #
as_rev(REV_ALEX)
ok("6. 🔴 a reviewer cannot delete another reviewer's note", status_of(lambda: main.review_clp_note_delete(Y_N, N_SAM["id"])) == 403)
ok("6. 🔴 ...nor the contractor's", status_of(lambda: main.review_clp_note_delete(Y_N, N_PAT["id"])) == 403)
as_rev(REV_SAM)
_c = main.review_clp_note_delete(Y_N, N_SAM["id"])
ok("6. ⭐ a reviewer deletes their own note", not any(n.get("id") == N_SAM["id"] for n in _c["thread"]))
ok("6. ...the task made from it keeps its words, no longer names the note",
   any(t["words"] == "Add the Gate B Saturday hours to 5" and t["from_note_by"] is None for t in _c["tasks"]))
ok("6. 🔴 a contractor row is never found through the review delete of another CLP",
   status_of(lambda: main.review_clp_note_delete(P_ALL, N_PAT["id"])) == 404)
as_(PAT)
ok("6. ⭐ a planner deletes the contractor's note in the client's tab", not any(
    n.get("id") == N_PAT["id"] for n in {c["name"]: c for c in main.clp_notes_delete(Y_N, N_PAT["id"])["thread"]["clients"]}["National Highways"]["notes"]))

# =========================================================================== #
#  7. Counts (Q8)                                                              #
# =========================================================================== #
_row = {c["id"]: c for c in clp_records.list_for(PAT)["clps"]}[Y_N]["tasks"]
_open_nh = [t for t in tab(Y_N, PAT, "National Highways")["tasks"] if not t["done"]]
ok("7. ⭐ the planner's list counts the client tab apart", _row["client_open"] == len(_open_nh) and _row["client_open"] >= 3
   and _row["client_mine_open"] == sum(1 for t in _open_nh if t["mine"]), str(_row))
ok("7. ...the contractor's own counts leave the client's out", _row["open"] == sum(
    1 for t in clp_notes.thread(Y_N, PAT, factors)["tasks"] if not t["done"]))
_row_n = {c["id"]: c for c in clp_records.list_for(NORA)["clps"]}[Y_N]["tasks"]
ok("7. 🔴 (Q4) the team's list counts no client task", _row_n["client_open"] == 0 and _row_n["client_mine_open"] == 0
   and _row_n["client_overdue"] == 0)
as_rev(REV_SAM)
_l = {c["id"]: c for c in main.review_clps()["clps"]}
ok("7. ⭐ the reviewer's list: tasks for the group or for them",
   _l[Y_N]["tasks_open"] == sum(1 for t in main.review_clp(Y_N)["tasks"] if not t["done"] and t["mine"]), str(_l[Y_N]))
as_rev(REV_ALEX)
ok("7. ...Alex's count has his own task too", {c["id"]: c for c in main.review_clps()["clps"]}[Y_N]["tasks_open"]
   == sum(1 for t in main.review_clp(Y_N)["tasks"] if not t["done"] and t["mine"]))
as_(PAT)
ok("7. the approve card's summary counts the client tab apart", clp_notes.open_summary(Y_N)["client_open"] == _row["client_open"])

# =========================================================================== #
#  8. 🔴 Another group                                                         #
# =========================================================================== #
as_rev(REV_HAL)
ok("8. 🔴 a CLP not sent to the group: every new review write is a 404",
   all(status_of(fn) == 404 for fn in (lambda: main.review_clp_task(Y_N, T(words="x", **{"for": "approvers"})),
                                         lambda: main.review_clp_task_change(Y_N, T_GROUP, T(done=True)),
                                         lambda: main.review_clp_task_delete(Y_N, T_GROUP),
                                         lambda: main.review_clp_note_delete(Y_N, N_PAT["id"]))))
as_(PAT)
_r = main.clp_tasks_add(Y_ALL, CT(words="National Highways only", group=NH["id"], **{"for": "group"}))
T_NH_ALL = _r["id"]
main.clp_notes_add(Y_ALL, main.ClpNoteIn(note="For National Highways only", group=NH["id"]))
as_rev(REV_HAL)
_c = main.review_clp(Y_ALL)
ok("8. 🔴 on a CLP sent to both, Harborough reads none of National Highways' tab",
   "National Highways only" not in json.dumps(_c) and _c["tasks"] == [], json.dumps(_c)[:300])
ok("8. 🔴 ...and cannot tick, change or delete its task (404, as missing)",
   status_of(lambda: main.review_clp_task_change(Y_ALL, T_NH_ALL, T(done=True))) == 404
   and status_of(lambda: main.review_clp_task_delete(Y_ALL, T_NH_ALL)) == 404)
_c = main.review_clp_task(Y_ALL, T(words="Harborough's own", **{"for": "approvers"}))
as_rev(REV_SAM)
ok("8. 🔴 National Highways reads none of Harborough's", "Harborough's own" not in json.dumps(main.review_clp(Y_ALL)))
as_(PAT)
ok("8. ⭐ the planner reads each in its own tab", any(t["words"] == "Harborough's own" for t in tab(Y_ALL, PAT, "Harborough District Council")["tasks"])
   and not any(t["words"] == "Harborough's own" for t in tab(Y_ALL, PAT, "National Highways")["tasks"]))

# =========================================================================== #
#  9. A stopped group; the Word file                                           #
# =========================================================================== #
as_(ADA)
clp_reviews.change_group(HDC["id"], stopped=True)
as_(PAT)
_hd = tab(Y_ALL, PAT, "Harborough District Council")
ok("9. a stopped group's tab stays readable, with nothing to write", _hd and _hd["stopped"] and not _hd["can_write"]
   and _hd["for_options"] == [] and any(t["words"] == "Harborough's own" for t in _hd["tasks"]))
ok("9. 🔴 nothing new is written to it", status_of(lambda: main.clp_notes_add(Y_ALL, main.ClpNoteIn(note="x", group=HDC["id"]))) == 422
   and status_of(lambda: main.clp_tasks_change(Y_ALL, [t for t in _hd["tasks"]][0]["id"], CT(done=True))) == 422)
as_(ADA)
clp_reviews.change_group(HDC["id"], stopped=False)
as_(PAT)
_hist = json.dumps(clp_records.doc_history(Y_N))
ok("9. ⭐ neither thread is in the issued file's history",
   "Saturday hours" not in _hist and "Bob owes" not in _hist and "traffic plan" not in _hist, _hist[:300])

# =========================================================================== #
# 10. By source                                                                #
# =========================================================================== #
NOTES_SRC = open(os.path.join(BACKEND, "clp_notes.py"), encoding="utf-8").read()
REVS_SRC = open(os.path.join(BACKEND, "clp_reviews.py"), encoding="utf-8").read()
ok("10. 🔴 every contractor read and write of a client row checks the approver first",
   NOTES_SRC.count("if rows and _client(rows[0]) and not access.can_approve(acc):") == 2
   and "clients = [client_thread(rec, g, all_rows, \"contractor\", acc) for g in sent_groups(rec[\"id\"])] if appr else []" in NOTES_SRC)
ok("10. 🔴 every reviewer write goes through the group's sends first",
   REVS_SRC.count("if cid not in _sent_to(rev):\n        return {\"error\": \"No such CLP.\", \"status\": 404}") == 4   # task, change_task, remove, comment
   and "sent = _sent_to(rev)\n    if cid not in sent:" in REVS_SRC)                       # decide
ok("10. 🔴 a reviewer's row lookup is by the reviewer's own group",
   REVS_SRC.count('clp_notes.client_row(cid, ') == 2 and 'rev["group_id"]' in REVS_SRC)
ok("10. the Show to tick's words are gone from the backend (Q2)", "Only a planner or an admin shows a note" not in NOTES_SRC)

# =========================================================================== #
# 11. From the review of this branch (31 Oct): a stopped tab's deletes, the     #
#     note of a decision, PR 3c's tasks made from a comment                     #
# =========================================================================== #
as_(PAT)
_r = main.clp_tasks_add(Y_ALL, CT(words="Harborough to confirm the bus route", group=HDC["id"], **{"for": "group"}))
T_HDC = _r["id"]
as_(ADA)
clp_reviews.change_group(HDC["id"], stopped=True)
as_(PAT)
ok("11. 🔴 a stopped group's tab takes no delete from the contractor either (422, as a tick)",
   status_of(lambda: main.clp_tasks_delete(Y_ALL, T_HDC)) == 422
   and any(t["id"] == T_HDC for t in tab(Y_ALL, PAT, "Harborough District Council")["tasks"]))
as_(ADA)
clp_reviews.change_group(HDC["id"], stopped=False)
as_(PAT)
ok("11. ...and once it is started again the planner deletes it", "deleted" in main.clp_tasks_delete(Y_ALL, T_HDC))

as_rev(REV_SAM)
main.review_clp_decision(Y_N, main.ReviewDecisionIn(issue_no=1, decision="returned", words="Section 5 still lacks the Saturday hours."))
_dn = [n for n in main.review_clp(Y_N)["thread"] if n["kind"] == "note" and n.get("words") == "Section 5 still lacks the Saturday hours."]
ok("11. 🔴 the note that went with the Return cannot be deleted by its writer (the decision's reason stays)",
   _dn and not _dn[0]["can_delete"] and status_of(lambda: main.review_clp_note_delete(Y_N, _dn[0]["id"])) == 403, str(_dn)[:200])
_mine = main.review_clp_comment(Y_N, main.ReviewCommentIn(words="A plain note of mine"))
_pn = [n for n in _mine["thread"] if n["kind"] == "note" and n.get("words") == "A plain note of mine"][0]
ok("11. ...a plain note of the reviewer's still can", _pn["can_delete"] and not any(n.get("id") == _pn["id"] for n in main.review_clp_note_delete(Y_N, _pn["id"])["thread"]))

# PR 3c's "Make a task" from a reviewer's comment: a contractor task For the team, carrying the comment's group
as_(PAT)
OLD3C = clp_notes._insert({"clp_id": Y_N, "kind": "task", "words": "INTERNAL: chase Bob for the gate hours", "for_kind": "team",
                           "for_team": "IPT1", "written_by": "Pat Planner", "written_key": f"u:{U_PAT['id']}",
                           "review_group": NH["id"]})
as_(NORA)
ok("11. (before the move) such a row sits in the client's tab, out of the team's sight",
   not any(t["id"] == OLD3C for t in clp_notes.thread(Y_N, NORA, factors)["tasks"]))
_mc = db.get_conn()
db._migrate_pre_3d_tasks(_mc.cursor())
_mc.commit()
_mc.close()
ok("11. ⭐ the first start of 3d puts PR 3c's tasks back in the contractor's tab: the team sees its task again",
   any(t["id"] == OLD3C and t["words"] == "INTERNAL: chase Bob for the gate hours" for t in clp_notes.thread(Y_N, NORA, factors)["tasks"]))
as_rev(REV_SAM)
_rv = main.review_clp(Y_N)
ok("11. 🔴 ...and the client no longer reads it", "chase Bob" not in json.dumps(_rv))
ok("11. ...a task a reviewer wrote stays in the client's tab, with the reviewer's notes",
   any(t["can_change"] for t in _rv["tasks"]) and any(n["kind"] == "note" and n["reviewer"] for n in _rv["thread"]))
ok("11. an organisation file from before 3d is read by the same rule (no from_note key = from before)",
   db.pre_3d_clp_note({"kind": "task", "review_group": "G1", "written_key": "u:x"})["review_group"] is None
   and db.pre_3d_clp_note({"kind": "task", "review_group": "G1", "written_key": "r:x"})["review_group"] == "G1"
   and db.pre_3d_clp_note({"kind": "note", "review_group": "G1", "written_key": "u:x"})["review_group"] == "G1"
   and db.pre_3d_clp_note({"kind": "task", "review_group": "G1", "written_key": "u:x", "from_note": None})["review_group"] == "G1")
DB_SRC = open(os.path.join(BACKEND, "db.py"), encoding="utf-8").read()
TP_SRC = open(os.path.join(BACKEND, "tenant_package.py"), encoding="utf-8").read()
ok("11. 🔴 the move runs only on the first start of 3d (the from_note column not there yet), and on an import",
   'first_3d = not _has_column(cur, "clp_notes", "from_note")' in DB_SRC and "if first_3d:\n                _migrate_pre_3d_tasks(cur)" in DB_SRC
   and 'rows = [db.pre_3d_clp_note(r) for r in rows]' in TP_SRC)

print(f"test_clp_client_thread: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
