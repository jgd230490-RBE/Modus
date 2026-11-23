"""
The "Working" list, the server's half (23 Nov 2026, branch claude/working-list; John's "Yes, as recommended" to Q1 to Q8
of the mockup notes/working-list-mockup-1121, Option A; notes/session-1123-working-list.md).

WHAT IS ASSERTED
  1. The record's store: one table, working_jobs, scoped by tenant but NOT package data (a re-import is itself a job and
     must not wipe its own row), made at start-up, in db.NO_DATA_TABLES; /api/working/ writes skip the audit and the bump.
  2. Nothing a job's row does moves db.data_version() (start, every batch's progress, end, close, the read).
  3. The words, made in one place: the mockup's own lines ("Route all: 62 of 188 legs", "R014: routing again, 1 of 4 lorry
     types", "Road closures: checking", "R050: Alt 1 made the main route", "Route all stopped at 62 of 188 legs").
  4. The refusal: the mockup's sentence word for word, and all 81 pairs in the one shape, "are / they finish" only for
     Busy-hour times.
  5. One job at a time, refused by the SERVER, for every pair: with each of the nine kinds running, each of the nine is
     refused where it is started (the page's start, Make primary, the re-import, the two fetches, the closures check)
     with that pair's sentence. One exception, as before: a second press of the closures check joins the one running.
  6. A batch of the job already running is never refused; another job's batch is; a call no page started runs when
     nothing is running; the batch endpoints move the row on and hand the line back.
  7. Stopped: no batch for GAP reads "stopped" and frees the slot; the row is in the database, so it still reads stopped
     after a restart; a held job the process no longer holds reads stopped at once; a late batch revives its own row;
     "Carry on" keeps the count; who may carry on.
  8. The list: running, stopped, done for 30 minutes, closed lines gone for everyone; the three server-run jobs read
     from their own state and never copied; a refused or rolled-back held request leaves no line.
  9. The routes: any staff sign-in reads, nobody and a client reviewer do not; a start needs an admin login.
 10. A zone write that would clear route legs is refused while a job runs; one that clears nothing is not; a haul road
     put on a route is.
 11. The words on a screen: no supplier, no back-end word, lorry not truck. The guides' entries exist.

WHAT THIS DOES NOT PROVE
  * No router call is made: network.bake_batch, network.bake_todo and hour_times.bake_batch are stand-ins here, so a real
    Route all, a real Busy-hour run and a real zone re-route are NOT run. No real fetch (community.refresh and
    collisions.refresh must never be reached here: each raises). No real re-import through this file (smoke harnesses do).
  * SQLite only: Postgres is not run. The lock is a thread lock and is not raced here.
  * The endpoints are called as functions on a stand-in FastAPI: the middleware (the audit skip, the header rule) is
    read at source level here; smoke_reviewer_wall.py and http_smoke.py run the real app.

Run:  python backend/tests/test_working.py
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

# ---- stubs, verbatim from test_gate_access.py ---------------------------------
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


_fa = types.ModuleType("fastapi")
_fa.FastAPI = _App
_fa.HTTPException = _HTTPException
_fa.Query = lambda default=None, **k: default


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
_resp.Response = object
sys.modules.setdefault("fastapi.responses", _resp)
_static = types.ModuleType("fastapi.staticfiles")


class _StaticFiles:
    def __init__(self, *a, **k):
        pass


_static.StaticFiles = _StaticFiles
sys.modules.setdefault("fastapi.staticfiles", _static)

TMP = tempfile.mkdtemp(prefix="wayscope_working_")
from portable import remove_scratch_db   # noqa: E402
for _v in ("DATABASE_URL", "ADMIN_TOKEN", "TENANT_ID", "HERE_API_KEY"):
    os.environ.pop(_v, None)

import db  # noqa: E402
db._SQLITE_PATH = os.path.join(TMP, "scratch.db")
import conversions  # noqa: E402
import network  # noqa: E402
import main  # noqa: E402
import access  # noqa: E402
import config  # noqa: E402
import costing  # noqa: E402
import community  # noqa: E402
import collisions  # noqa: E402
import fetch_guard  # noqa: E402
import haul  # noqa: E402
import hour_times  # noqa: E402
import limits  # noqa: E402
import restrictions  # noqa: E402
import tenant_package  # noqa: E402
import zones  # noqa: E402

PASS = 0
FAIL = []


def ok(label, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{label} {extra}".strip())


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


remove_scratch_db(db, TMP)
db.init_db(); db.init_network_db(); db.init_taxonomy_db(); db.init_zones_db(); db.init_gates_db()
db.init_weeks_db(); db.init_lookahead_db(); db.init_config_db(); db.init_costing_db()
limits.init_db(); db.init_tenant()
config.invalidate(); config.seed_from_file(conversions); config.invalidate(); costing.invalidate()

try:
    import working  # noqa: E402
except Exception as e:      # the code before: no module
    working = None
    FAIL.append(f"⭐ backend/working.py imports ({e})")

T = db.current_tenant()
ADMIN = {"via": "login", "role": "admin", "name": "Ada Admin", "can_approve": True}
PLANNER = {"via": "login", "role": "planner", "name": "Pat Planner", "can_approve": True}
TEAM = {"via": "login", "role": "ipt", "ipt": "IPT1", "name": "Tom Team"}
ADMIN_CODE = {"via": "code", "role": "admin", "label": "Admin"}


def as_(acc):
    access._ACCESS.set(acc)


def http(fn, *a, **k):
    """Call an endpoint as a function: ("ok", answer) or (status, detail)."""
    try:
        return "ok", fn(*a, **k)
    except _HTTPException as e:
        return e.status_code, e.detail


def iso(minutes_ago=0):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)).replace(
        microsecond=0).isoformat().replace("+00:00", "Z")


def wipe():
    """Nothing running, nothing in the list."""
    if working:
        working._rows()          # (the table, where this scratch database has none yet)
        db.execute("DELETE FROM working_jobs WHERE tenant_id = ?", (T,))
        working._HELD.clear()
    for tbl in ("community_meta", "collision_meta"):
        db.execute(f"DELETE FROM {tbl} WHERE tenant_id = ?", (T,))
    restrictions._REFRESH.update({"running": False, "started_at": None, "finished_at": None, "status": None, "error": None})


MAIN = read("backend/main.py")
if working:
    # the stand-ins: no router, no fetch
    def _never(*a, **k):
        raise AssertionError("a real fetch was reached")
    community.refresh = _never
    collisions.refresh = _never
    restrictions.current = lambda: {"ui_label": "Road closures (National Highways)", "key": "nh_closures"}
    _real_todo = getattr(network, "bake_todo", None)
    network.bake_todo = lambda profile=None, legs=None: 94
    network.bake_batch = lambda **k: {"profile": k.get("profile"), "baked": 30, "errors": 0, "attempted": 31, "remaining": 63}
    hour_times.bake_batch = lambda **k: {"baked": 30, "errors": 0, "attempted": 30, "remaining": 824}
    hour_times.clear = lambda *a, **k: {"cleared": True}
    wipe()

    # ======================================================================= #
    #  1. The record's store                                                   #
    # ======================================================================= #
    DB = read("backend/db.py")
    ddl = DB.split("CREATE TABLE IF NOT EXISTS working_jobs (")[1].split('""")')[0] if "working_jobs (" in DB else ""
    ok("⭐ 1. one table working_jobs, keyed (tenant_id, id), made by db.init_working_db at start-up",
       "PRIMARY KEY (tenant_id, id)" in ddl and "db.init_working_db()" in MAIN
       and MAIN.index("db.init_working_db()") < MAIN.index("db.init_tenant()"))
    ok("⭐ 1. NOT package data: not a TENANTED table, not in the organisation file (a re-import must not wipe its own row)",
       "working_jobs" not in db.TENANTED_TABLES and "working_jobs" not in tenant_package.ORDER
       and "working_jobs" not in read("backend/tools/make_demo_tenant.py"))
    ok("⭐ 1. in db.NO_DATA_TABLES (a batch's progress must not empty the kept reads)", "working_jobs" in db.NO_DATA_TABLES)
    ok("1. ...and named with its reason in the tenant audit's list of tables that are not package data",
       '"working_jobs":' in read("backend/tests/test_tenant_audit.py"))
    ok("1. no REAL and no BOOLEAN column (Postgres: float4; never compare a BOOLEAN with 1)",
       ddl and " REAL" not in ddl.upper() and "BOOLEAN" not in ddl.upper())
    ok("⭐ 1. the list's own writes write no audit row and bump nothing in the middleware (/api/working/ is skipped)",
       "/api/working/" in main.AUDIT_SKIP_PREFIXES and not main._audited("/api/working/start")
       and not main._audited("/api/working/abc/end") and not main._audited("/api/working/abc/close")
       and main._audited("/api/admin/bake-routes") and main._audited("/api/admin/tenant/import"))
    _wsrc = read("backend/working.py")
    _stmts = [m.start() for m in re.finditer(r'"(?:SELECT|INSERT INTO|UPDATE|DELETE FROM)[^"]*working_jobs', _wsrc)]
    ok("1. every statement on the table filters on tenant_id",
       len(_stmts) >= 8 and all("tenant_id" in _wsrc[i:i + 420] for i in _stmts), f"{len(_stmts)} statements")
    # a database that never went through the lifespan gets the table on the first read
    db.execute("DROP TABLE IF EXISTS working_jobs")
    ok("1. a database without the table gets it on the first read (no job endpoint fails for want of the list)",
       working.listing(ADMIN)["jobs"] == [] and working.refusal("route_all") is None)

    # ======================================================================= #
    #  2. No data version moved                                                #
    # ======================================================================= #
    v0 = db.data_version()
    j = working.start("route_all", by="Ada Admin", total=188, detail={"args": {"profiles": ["A", "B"], "legs": ""}})
    for _ in range(3):
        working.progress(j["id"], attempted=20, remaining=100)
    working.listing(ADMIN)
    working.end(j["id"], "stopped")
    j2 = working.start("route_all", by="Ada Admin", total=128, carry=j["id"])
    working.end(j2["id"], "done")
    working.close(j2["id"], ADMIN)
    with working.held("make_primary", by="Ada Admin", subject="R050", detail={"label": "Alt 1"}) as h:
        h.done()
    ok("⭐ 2. a start, three batches, the read, a stop, a carry on, an end, a close and a held job move db.data_version() by 0",
       db.data_version() == v0, f"moved by {db.data_version() - v0}")
    db.execute("DELETE FROM routes WHERE tenant_id = ? AND id = ?", (T, "none"))
    ok("2. ...while a write to a data table still moves it (the check is not vacuous)", db.data_version() == v0 + 1)
    wipe()

    # ======================================================================= #
    #  3. The words (the mockup's cards 1 and 2)                               #
    # ======================================================================= #
    L = working.line
    ok("⭐ 3. card 2's three lines, word for word",
       L("route_all", "running", 62, 188) == "Route all: 62 of 188 legs"
       and L("route_again", "running", 0, 4, "R014") == "R014: routing again, 1 of 4 lorry types"
       and L("closures", "running") == "Road closures: checking",
       " | ".join([L("route_all", "running", 62, 188), L("route_again", "running", 0, 4, "R014"), L("closures", "running")]))
    ok("⭐ 3. card 1's done and stopped rows, word for word",
       L("make_primary", "done", 0, None, "R050", {"label": "Alt 1"}) == "R050: Alt 1 made the main route"
       and L("route_all", "stopped", 62, 188) == "Route all stopped at 62 of 188 legs"
       and working.KINDS["route_all"]["kept"] == "the routes worked out are kept")
    ok("3. the other kinds in the one shape (the job, then how far)",
       L("hour_times", "running", 240, 854) == "Busy-hour times: 240 of 854 worked out"
       and L("zone_reroute", "running", 12, 40) == "Zone re-route: 12 of 40 legs"
       and L("community", "running") == "Community places: fetching" and L("collisions", "done") == "Collision history: fetched"
       and L("import", "running") == "Organisation file: replacing" and L("import", "done") == "Organisation file: replaced"
       and L("route_again", "done", 4, 4, "R014") == "R014: routed again"
       and L("route_again", "running", 0, 1, "R014") == "R014: routing again, 1 of 1 lorry type"
       and L("route_all", "done", 188, 188) == "Route all: 188 legs" and L("zone_reroute", "done", 1, 1) == "Zone re-route: 1 leg")
    ok("3. a row is 8 words at most at these sizes (the mockup's count)",
       all(len(x.split()) <= 8 for x in (L("route_all", "running", 62, 188), L("route_all", "stopped", 62, 188),
                                         L("route_again", "running", 0, 4, "R014"), L("hour_times", "running", 240, 854),
                                         L("make_primary", "done", 0, None, "R050", {"label": "Alt 1"}),
                                         L("zone_reroute", "running", 12, 40), L("community", "running"))))
    restrictions.current = lambda: {"ui_label": "Road restrictions (Tark Tee)"}
    ok("3. the closures check takes the country's own name, never its provider's",
       L("closures", "running") == "Road restrictions: checking" and working.name_of("closures") == "The road restrictions check")
    restrictions.current = lambda: {"ui_label": "Road closures (National Highways)", "key": "nh_closures"}

    # ======================================================================= #
    #  4. The refusal sentence                                                 #
    # ======================================================================= #
    S = working.sentence
    ok("⭐ 4. card 3's sentence, word for word (12 words)",
       S("hour_times", "route_all") == "Busy-hour times are running. Route all can start when they finish."
       and len(re.findall(r"[A-Za-z]+", S("hour_times", "route_all"))) == 12, S("hour_times", "route_all"))
    ok("⭐ 4. 'Route all is running.' (singular) the other way round",
       S("route_all", "hour_times") == "Route all is running. Busy-hour times can start when it finishes.")
    SHAPE = re.compile(r"^(.+) (is|are) running\. (.+) can start when (it finishes|they finish)\.$")
    bad = []
    for a in working.KINDS:
        for b in working.KINDS:
            m = SHAPE.match(S(a, b))
            plural = a == "hour_times"
            if not m or m.group(1) != working.name_of(a) or m.group(3) != working.name_of(b) \
                    or (m.group(2) == "are") != plural or (m.group(4) == "they finish") != plural:
                bad.append(S(a, b))
    ok("⭐ 4. all 81 pairs: the one shape, each job by its own name, 'are / they finish' only for Busy-hour times",
       len(working.KINDS) == 9 and not bad, "; ".join(bad[:4]))
    ok("4. each job's name starts a sentence (a capital) and none is longer than 5 words",
       all(working.name_of(k)[0].isupper() and len(working.name_of(k).split()) <= 5 for k in working.KINDS))
    ok("⭐ 4. fetch_guard's two sentences are gone; its lock is the list's one lock",
       not hasattr(fetch_guard, "BUSY_WORDS") and not hasattr(fetch_guard, "other_running") and working.LOCK is fetch_guard.LOCK)

    # ======================================================================= #
    #  5. One job at a time, for every pair                                    #
    # ======================================================================= #
    def make_running(kind):
        wipe()
        if working.KINDS[kind]["by"] == "page":
            return working.start(kind, by="Ada Admin", total=40, subject="R014" if kind == "route_again" else None)["id"]
        if working.KINDS[kind]["by"] == "held":
            return working.start(kind, by="Ada Admin", subject="R050" if kind == "make_primary" else None,
                                 detail={"label": "Alt 1"}, held=True)["id"]
        if kind == "community":
            community._write_meta("running", {}, by="Ada Admin", started_at=iso())
        elif kind == "collisions":
            collisions._write_meta("running", {}, by="Ada Admin", started_at=iso())
        else:
            restrictions._REFRESH.update({"running": True, "started_at": iso(), "finished_at": None})
        return None

    def attempt(kind):
        """Ask for `kind` where a person would start it: (refused?, the words)."""
        as_(ADMIN)
        if working.KINDS[kind]["by"] == "page":
            st, d = http(main.working_start, main.WorkStartIn(kind=kind, total=4, subject="R020", profiles=["A"]))
            return st == working.BUSY_STATUS, d
        if kind == "make_primary":
            st, d = http(main.promote_alt, "R020", "A", 1, "loaded", None, None)
            return st == working.BUSY_STATUS, d
        if kind == "import":
            st, d = http(main.tenant_import, {}, 1, None)
            return st == working.BUSY_STATUS, d
        if kind == "community":
            r = community.start_refresh(by="Ada Admin", sync=True)
            return r.get("started") is False, r.get("message")
        if kind == "collisions":
            r = collisions.start_refresh(by="Ada Admin", sync=True)
            return r.get("started") is False, r.get("message")
        st, d = http(main.forecast_week_restrictions_refresh)
        return st == working.BUSY_STATUS, d

    for a in working.KINDS:
        wrong = []
        for b in working.KINDS:
            make_running(a)
            if a == "closures" and b == "closures":
                continue                       # a second press joins the check running (asserted below)
            refused, words = attempt(b)
            if not refused or words != S(a, b):
                wrong.append(f"{b}: {refused} {words!r}")
        ok(f"⭐ 5. with {working.name_of(a)} running, every other start is refused by the server in that pair's sentence",
           not wrong, "; ".join(wrong[:3]))
    make_running("closures")
    limits.store_checks = lambda *a, **k: None
    st, d = http(main.forecast_week_restrictions_refresh)
    ok("5. ...a second press of the closures check joins the one running, as before (no refusal)",
       st == "ok" and d.get("running") is True, f"{st} {d}")
    wipe()
    as_(ADMIN)
    st, d = http(main.working_start, main.WorkStartIn(kind="route_all", profiles=["A", "B"]))
    ok("5. with nothing running a start is taken, and Route all's total is the legs to do over its lorry types",
       st == "ok" and d["state"] == "running" and d["total"] == 188 and d["line"] == "Route all: 0 of 188 legs"
       and d["by"] == "Ada Admin", f"{st} {d}")
    st2, d2 = http(main.working_start, main.WorkStartIn(kind="route_all", profiles=["A"]))
    ok("⭐ 5. ...and a second Route all, from anyone, is refused: 'Route all is running. Route all can start when it finishes.'",
       st2 == 423 and d2 == "Route all is running. Route all can start when it finishes.", f"{st2} {d2}")
    ok("5. a start of something that is not a page-sent job is a 400, not a row",
       http(main.working_start, main.WorkStartIn(kind="community"))[0] == 400
       and http(main.working_start, main.WorkStartIn(kind="nonsense"))[0] == 400)

    # ======================================================================= #
    #  6. Batches                                                              #
    # ======================================================================= #
    job = d["id"]
    st, r = http(main.bake_routes, "A", 30, None, None, job)
    ok("⭐ 6. a batch of the job already running is never refused, moves the row on and hands back its line",
       st == "ok" and r["working"]["line"] == "Route all: 31 of 188 legs" and r["working"]["done"] == 31, f"{st} {r}")
    st, r = http(main.bake_routes, "A", 30, None, None, None)
    ok("6. ...nor is the same job's batch from a page that sent no job id (the same work)",
       st == "ok" and r["working"]["done"] == 62 and r["working"]["line"] == "Route all: 62 of 188 legs", f"{st} {r}")
    st, r = http(main.hour_times_bake, 30, None, None)
    ok("⭐ 6. another job's batch is refused while Route all runs, in the sentence",
       st == 423 and r == "Route all is running. Busy-hour times can start when it finishes.", f"{st} {r}")
    st, r = http(main.hour_times_clear, None, None)
    ok("6. ...and its clear (nothing is dropped while another job runs)", st == 423)
    st, r = http(main.bake_route, "R014", "A", None, False, None, "no-such-job")
    ok("6. ...and a Route again request carrying a job id", st == 423 and r == "Route all is running. Route again can start when it finishes.", f"{st} {r}")
    working.end(job, "done")
    network.bake_route = lambda *a, **k: {"route_id": a[0], "baked": 2}
    st, r = http(main.bake_route, "R014", "A", None, False, None, None)
    ok("6. a new or edited route's own bake (no job id) is not part of the list: never refused, no row, no line",
       st == "ok" and "working" not in r and not [x for x in working.listing(ADMIN)["jobs"] if x["kind"] == "route_again"])
    wipe()
    st, r = http(main.bake_routes, "A", 30, None, None, None)
    ok("6. with nothing running, a batch no page started still runs (and keeps no row)",
       st == "ok" and "working" not in r and working.listing(ADMIN)["jobs"] == [])
    st, hj = http(main.working_start, main.WorkStartIn(kind="hour_times"))
    st, r = http(main.hour_times_bake, 30, None, hj["id"])
    ok("6. Busy-hour times with no total at the start takes it from its first batch",
       st == "ok" and r["working"]["line"] == "Busy-hour times: 30 of 854 worked out", f"{st} {r}")
    st, e = http(main.working_end, hj["id"], main.WorkEndIn(state="done"))
    ok("6. the page's end marks the row done, with its done line", st == "ok" and e["state"] == "done"
       and e["line"] == "Busy-hour times: 854 worked out")
    st, ra = http(main.working_start, main.WorkStartIn(kind="route_again", subject="R014", profiles=["A", "B", "C", "D"]))
    ok("6. Route again's row: the mockup's line at the start", st == "ok" and ra["line"] == "R014: routing again, 1 of 4 lorry types")
    st, r = http(main.bake_route, "R014", "A", None, False, None, ra["id"])
    ok("6. ...and after one lorry type", st == "ok" and r["working"]["line"] == "R014: routing again, 2 of 4 lorry types"
       and r["working"]["done"] == 1, f"{st} {r}")
    working.end(ra["id"], "stopped")
    ok("6. ...stopped there: 'R014: routing again stopped at 1 of 4 lorry types'",
       working.view(working._get(ra["id"]))["line"] == "R014: routing again stopped at 1 of 4 lorry types")
    wipe()

    # ======================================================================= #
    #  7. Stopped                                                              #
    # ======================================================================= #
    as_(ADMIN)
    j = working.start("route_all", by="Ada Admin", total=188, detail={"args": {"profiles": ["A", "B"], "legs": "loaded"}})
    working.progress(j["id"], attempted=62, remaining=126)
    ok("7. the gap is five minutes", working.GAP == datetime.timedelta(minutes=5))
    db.execute("UPDATE working_jobs SET beat_at = ? WHERE tenant_id = ? AND id = ?", (iso(4), T, j["id"]))
    ok("7. four minutes without a batch: still running, still the only job", working.listing(ADMIN)["jobs"][0]["state"] == "running"
       and working.refusal("hour_times") is not None)
    db.execute("UPDATE working_jobs SET beat_at = ? WHERE tenant_id = ? AND id = ?", (iso(6), T, j["id"]))
    row = working.listing(ADMIN)["jobs"][0]
    ok("⭐ 7. six minutes without a batch: 'Route all stopped at 62 of 188 legs', what it worked out kept, the slot free",
       row["state"] == "stopped" and row["line"] == "Route all stopped at 62 of 188 legs"
       and row["kept"] == "the routes worked out are kept" and row["ended_at"] and working.refusal("hour_times") is None
       and working.listing(ADMIN)["busy"] == {}, str(row))
    ok("⭐ 7. the row is in the database: after a restart (nothing in memory) it still reads stopped, with what Carry on needs",
       (working._HELD.clear() or True) and working.listing(ADMIN)["jobs"][0]["state"] == "stopped"
       and working.listing(ADMIN)["jobs"][0]["args"] == {"profiles": ["A", "B"], "legs": "loaded"})
    ok("7. Carry on is offered to an admin login only (who may start Route all), never to a planner, a team or a code",
       working.listing(ADMIN)["jobs"][0]["can_carry"] is True and working.listing(PLANNER)["jobs"][0]["can_carry"] is False
       and working.listing(TEAM)["jobs"][0]["can_carry"] is False and working.listing(ADMIN_CODE)["jobs"][0]["can_carry"] is False)
    st, r = http(main.bake_routes, "A", 30, None, None, j["id"])
    ok("7. a late batch of a job that read stopped, with nothing else running, revives its own row",
       st == "ok" and r["working"]["state"] == "running" and r["working"]["done"] == 93, f"{st} {r}")
    working.end(j["id"], "stopped")
    network.bake_todo = lambda profile=None, legs=None: 47 if legs == ("loaded",) else 999
    st, c = http(main.working_start, main.WorkStartIn(kind="route_all", profiles=["A", "B"], legs="loaded", carry=j["id"]))
    ok("⭐ 7. Carry on starts a new row that keeps the count ('93 of 187 legs', what is left added to what was done)",
       st == "ok" and c["line"] == "Route all: 93 of 187 legs" and c["args"] == {"profiles": ["A", "B"], "legs": "loaded"}
       and [x["id"] for x in working.listing(ADMIN)["jobs"]] == [c["id"]], f"{st} {c}")
    wipe()
    h = working.start("make_primary", by="Ada Admin", subject="R050", detail={"label": "Alt 1"}, held=True)
    ok("7. a held job (Make primary) is running while this process holds it", working.listing(ADMIN)["jobs"][0]["state"] == "running")
    working._HELD.clear()
    row = working.listing(ADMIN)["jobs"][0]
    ok("⭐ 7. ...and reads stopped at once when the process no longer holds it (a restart), with no Carry on and a close",
       row["state"] == "stopped" and row["line"] == "R050: Make primary stopped" and row["can_carry"] is False
       and row["can_close"] is True and working.refusal("route_all") is None, str(row))
    db.execute("UPDATE working_jobs SET beat_at = ?, started_at = ? WHERE tenant_id = ? AND id = ?", (iso(31), iso(31), T, h["id"]))
    ok("7. ...and leaves the list after 30 minutes", working.listing(ADMIN)["jobs"] == [])
    wipe()

    # ======================================================================= #
    #  8. The list                                                             #
    # ======================================================================= #
    a = working.start("zone_reroute", by="Ada Admin", total=40, detail={"args": {"profiles": ["A"]}})
    working.progress(a["id"], attempted=40, remaining=0)
    working.end(a["id"], "done")
    b = working.start("route_again", by="Pat Planner", total=4, subject="R014")
    working.progress(b["id"], attempted=1)
    working.end(b["id"], "stopped")
    c = working.start("hour_times", by="Ada Admin", total=854)
    lst = working.listing(ADMIN)
    ok("⭐ 8. the list: what is running first, then what stopped part-way, then what is done",
       [x["state"] for x in lst["jobs"]] == ["running", "stopped", "done"]
       and [x["line"] for x in lst["jobs"]] == ["Busy-hour times: 0 of 854 worked out",
                                                "R014: routing again stopped at 1 of 4 lorry types", "Zone re-route: 40 legs"],
       str([x["line"] for x in lst["jobs"]]))
    ok("8. each row says where it runs, when it started, who started it, and what the page may do with it",
       [x["page"] for x in lst["jobs"]] == ["routes", "routes", "zones"] and all(x["started_at"] for x in lst["jobs"])
       and [x["by"] for x in lst["jobs"]] == ["Ada Admin", "Pat Planner", "Ada Admin"]
       and [x["can_close"] for x in lst["jobs"]] == [False, False, True]
       and [x["can_carry"] for x in lst["jobs"]] == [False, True, False])
    ok("⭐ 8. `busy` carries the refusal for each of the nine kinds while something runs (the page makes no sentence)",
       lst["running"] == "hour_times" and set(lst["busy"]) == set(working.KINDS)
       and lst["busy"]["route_all"] == "Busy-hour times are running. Route all can start when they finish.")
    as_(ADMIN)
    ok("8. a running line cannot be closed", http(main.working_close, c["id"])[0] == 404)
    as_(TEAM)
    st, after = http(main.working_close, a["id"])
    ok("⭐ 8. a finished line is closed by any staff sign-in, and is gone for everyone",
       st == "ok" and a["id"] not in [x["id"] for x in after["jobs"]]
       and a["id"] not in [x["id"] for x in working.listing(ADMIN)["jobs"]])
    ok("8. a stopped line is not closed by someone who may not start that job (it would take Carry on away)",
       http(main.working_close, b["id"])[0] == 404 and b["id"] in [x["id"] for x in working.listing(ADMIN)["jobs"]])
    working.end(c["id"], "done")
    db.execute("UPDATE working_jobs SET ended_at = ? WHERE tenant_id = ? AND id = ?", (iso(29), T, c["id"]))
    in29 = c["id"] in [x["id"] for x in working.listing(ADMIN)["jobs"]]
    db.execute("UPDATE working_jobs SET ended_at = ? WHERE tenant_id = ? AND id = ?", (iso(31), T, c["id"]))
    ok("⭐ 8. a finished line stays 30 minutes (there at 29, gone at 31)", in29 and c["id"] not in [x["id"] for x in working.listing(ADMIN)["jobs"]]
       and working.KEEP == datetime.timedelta(minutes=30))
    wipe()
    # the three the server runs: read from their own state
    community._write_meta("running", {}, by="Pat Planner", started_at=iso(3))
    row = working.listing(PLANNER)["jobs"][0]
    ok("⭐ 8. a community fetch running is in the list from its own state ('Community places: fetching'), no row copied",
       row["kind"] == "community" and row["state"] == "running" and row["line"] == "Community places: fetching"
       and row["by"] == "Pat Planner" and row["page"] == "config"
       and db.query("SELECT COUNT(*) AS n FROM working_jobs WHERE tenant_id = ?", (T,))[0]["n"] == 0, str(row))
    community._write_meta("done", {}, fetched_at=iso(2))
    row = working.listing(PLANNER)["jobs"][0]
    ok("8. ...done two minutes ago: 'Community places: fetched', with a close", row["state"] == "done"
       and row["line"] == "Community places: fetched" and row["can_close"] is True)
    as_(PLANNER)
    st, after = http(main.working_close, row["id"])
    ok("8. ...closed: gone, and only 'this line was closed' is stored", st == "ok" and after["jobs"] == []
       and [r["closed"] for r in db.query("SELECT closed FROM working_jobs WHERE tenant_id = ?", (T,))] == [1])
    community._write_meta("done", {}, fetched_at=iso(0))
    ok("8. ...a later fetch is a new line", len(working.listing(PLANNER)["jobs"]) == 1)
    wipe()
    collisions._write_meta("failed", {"error": "the fetch stopped: x"}, started_at=iso(5))
    row = working.listing(PLANNER)["jobs"][0]
    ok("8. a fetch that failed in the last 30 minutes reads stopped, with Carry on for a planner or an admin, not a team",
       row["state"] == "stopped" and row["line"] == "Collision history: fetch stopped" and row["can_carry"] is True
       and working.listing(TEAM)["jobs"][0]["can_carry"] is False, str(row))
    wipe()
    restrictions._REFRESH.update({"running": False, "started_at": iso(2), "finished_at": iso(1), "status": "ok"})
    row = working.listing(TEAM)["jobs"][0]
    ok("8. the closures check, finished a minute ago: 'Road closures: checked' on the Look-ahead's page",
       row["line"] == "Road closures: checked" and row["state"] == "done" and row["page"] == "lookahead")
    restrictions._REFRESH.update({"finished_at": iso(1), "status": "unavailable"})
    ok("8. ...and one that could not reach its source reads stopped, with Carry on for any staff sign-in",
       working.listing(TEAM)["jobs"][0]["line"] == "Road closures: check stopped" and working.listing(TEAM)["jobs"][0]["can_carry"] is True)
    wipe()
    # a held request that refuses or fails leaves no line
    network.promote_alternative = lambda *a, **k: {"error": "that alternative is not stored"}
    as_(ADMIN)
    st, r = http(main.promote_alt, "R050", "A", 1, "loaded", None, None)
    ok("8. a Make primary that refuses for its own reason leaves no line", st == "ok" and r.get("error") and working.listing(ADMIN)["jobs"] == [])
    network.promote_alternative = lambda *a, **k: {"route_id": a[0], "promoted": 1, "best": None}
    st, r = http(main.promote_alt, "R050", "A", 1, "loaded", None, None)
    row = (working.listing(ADMIN)["jobs"] or [{}])[0]
    ok("⭐ 8. a Make primary that moved the route leaves the mockup's done row: 'R050: Alt 1 made the main route'",
       st == "ok" and r.get("promoted") == 1 and row.get("line") == "R050: Alt 1 made the main route" and row.get("state") == "done"
       and row.get("by") == "Ada Admin" and row.get("can_close") is True, f"{st} {row}")
    wipe()

    def _boom(*a, **k):
        raise ValueError("not an organisation file")
    tenant_package.import_tenant = _boom
    st, r = http(main.tenant_import, {}, 1, None)
    ok("8. a re-import that is refused keeps its own answer (400) and leaves no line", st == 400 and working.listing(ADMIN)["jobs"] == [])
    tenant_package.import_tenant = lambda body, replace=False: {"imported": True}
    st, r = http(main.tenant_import, {}, 1, None)
    ok("⭐ 8. a re-import that worked leaves 'Organisation file: replaced' (Q8: the ninth job)",
       st == "ok" and [x["line"] for x in working.listing(ADMIN)["jobs"]] == ["Organisation file: replaced"])
    wipe()

    # ======================================================================= #
    #  9. The routes                                                           #
    # ======================================================================= #
    working.start("route_all", by="Ada Admin", total=10)
    as_(None)
    ok("⭐ 9. the read is refused to nobody, and so to a client reviewer (whose session gives no staff access)",
       http(main.working_list)[0] == 401 and "acc = _require_access()\n    return working.listing(acc)" in MAIN)
    as_(TEAM)
    st, r = http(main.working_list)
    ok("⭐ 9. any staff sign-in reads the list (a team sees the job and the refusal)", st == "ok" and r["jobs"][0]["line"] == "Route all: 0 of 10 legs"
       and r["busy"]["closures"].startswith("Route all is running."))
    for who, acc in (("a team", TEAM), ("a planner", PLANNER), ("a shared admin code", ADMIN_CODE)):
        as_(acc)
        ok(f"9. a start is an admin login's (the batches are): refused to {who}",
           http(main.working_start, main.WorkStartIn(kind="hour_times"))[0] == 403)
    as_(None)
    ok("9. ...and the end and the close to nobody", http(main.working_end, "x", main.WorkEndIn())[0] == 403
       and http(main.working_close, "x")[0] == 401)
    ok("9. the list's routes come after _gate_arrivals_build in main.py",
       MAIN.index("def _gate_arrivals_build") < MAIN.index('@app.get("/api/working")'))
    ok("9. the reviewer wall reads its routes from the app itself, so the four new ones are swept",
       "APIRoute" in read("backend/tests/smoke_reviewer_wall.py"))
    wipe()

    # ======================================================================= #
    # 10. A zone write                                                         #
    # ======================================================================= #
    as_(ADMIN)
    SQ = {"type": "Polygon", "coordinates": [[[-1.0, 52.5], [-0.9, 52.5], [-0.9, 52.6], [-1.0, 52.6], [-1.0, 52.5]]]}
    _real_inval = zones.invalidate
    asked = []

    def _inval(**k):
        asked.append(k.get("dry_run"))
        return {"leg_count": 3, "legs": [], "here_calls": 3} if k.get("dry_run") else _real_inval(**k)
    zones.invalidate = _inval
    n0 = len(zones.list_zones(include_inactive=True))
    st, z = http(main.create_zone, main.ZoneIn(name="Advisory", geometry=SQ, kind="other", affects_routing=False), None)
    ok("10. with nothing running a zone save asks no dry run for the list and saves", st == "ok" and asked.count(True) <= 1
       and len(zones.list_zones(include_inactive=True)) == n0 + 1, f"{st}")
    working.start("route_all", by="Ada Admin", total=10)
    st, r = http(main.create_zone, main.ZoneIn(name="Closure", geometry=SQ, kind="other", affects_routing=True), None)
    ok("⭐ 10. while Route all runs, a zone save that would clear route legs is refused in the sentence, and nothing is saved",
       st == 423 and r == "Route all is running. Zone re-route can start when it finishes."
       and len(zones.list_zones(include_inactive=True)) == n0 + 1, f"{st} {r}")
    st, r = http(main.create_zone, main.ZoneIn(name="Advisory 2", geometry=SQ, kind="other", affects_routing=False), None)
    ok("⭐ 10. ...a zone save that clears nothing is not a job: it goes through while Route all runs",
       st == "ok" and len(zones.list_zones(include_inactive=True)) == n0 + 2, f"{st} {r}")
    zid = z["zone"]["id"]
    st, r = http(main.update_zone, zid, main.ZoneIn(name="Advisory", geometry=SQ, kind="other", affects_routing=True), None)
    ok("10. ...an edit that would clear legs is refused, the zone as it was",
       st == 423 and zones.get_zone(zid)["affects_routing"] in (False, 0), f"{st} {r}")
    st, r = http(main.delete_zone, zid, None)
    ok("10. ...and a delete that would", st == 423 and zones.get_zone(zid) is not None, f"{st} {r}")
    st, r = http(main.attach_haul_road, "R014", main.HaulLinkIn(zone_id=zid), None)
    ok("10. ...and a haul road put on a route (it clears the route's legs for the page to route again)",
       st == 423 and r == "Route all is running. Zone re-route can start when it finishes.", f"{st} {r}")
    zones.invalidate = _real_inval
    wipe()

    # ======================================================================= #
    # 11. Words and guides                                                     #
    # ======================================================================= #
    said = [S(a, b) for a in working.KINDS for b in working.KINDS]
    for k in working.KINDS:
        for stt in ("running", "stopped", "done"):
            said.append(L(k, stt, 1, 4, "R014", {"label": "Alt 1"}))
        said.append(working.KINDS[k]["kept"])
    BAN = ("HERE", "OpenStreetMap", "National Highways", "DfT", "server", "batch", "endpoint", "token", "cached",
           "geometry", "bake", "truck", "job id", "thread")
    hits = sorted({w for w in BAN for s_ in said if re.search(r"\b" + re.escape(w) + r"\b", s_)})
    ok("⭐ 11. no supplier, no back-end word and no 'truck' in any line or refusal a person reads", not hits, str(hits))
    HTML = read("frontend/index.html")
    ok("⭐ 11. the 'i' box's words are the mockup's, word for word, and link to the user guide's entry",
       '"work.list": { title: "Working", text: "Long jobs run one at a time. You can leave the page: the job carries on and '
       'this list says when it is done.", guide: "ug-working-list" }' in HTML
       and 'id="ug-working-list"' in read("frontend/help/index.html"))
    UG = read("frontend/help/index.html")
    ug = UG[UG.index('id="ug-working-list"'):UG.index('id="2-3-on-the-demo-scheme-the-bar-and-the-tour"')]
    ok("11. the user guide's entry: one at a time, the chip, the stopped line and Carry on, 30 minutes, in plain words",
       all(w in ug for w in ("one at a time", "<strong>Working</strong>", "<strong>Carry on</strong>", "30 minutes",
                             "Busy-hour times are running. Route all can start when they finish."))
       and not re.search(r"\b(server|endpoint|batch|token|HERE|database|API)\b", re.sub(r"<[^>]+>", " ", ug)))
    TG = read("frontend/help/technical/index.html")
    ok("11. the technical guide's paragraph: the record, the stopped gap and the refusal",
       'id="t4-working"' in TG and "working_jobs" in TG and "working.GAP" in TG and "423" in TG
       and "db.NO_DATA_TABLES" in TG[TG.index('id="t4-working"'):TG.index('id="t4-working"') + 1200])

if not working:
    # the code before this branch: every starred check above fails by name (none of them can run without the module)
    with open(os.path.abspath(__file__), encoding="utf-8") as _f:
        for _lab in re.findall(r'^ +ok\(f?"(⭐[^"]*)"', _f.read(), flags=re.M):
            FAIL.append(_lab + "  (no backend/working.py)")

print(f"\ntest_working.py: {PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
